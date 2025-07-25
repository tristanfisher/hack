#!/usr/bin/env python3
from datetime import datetime, timezone
from typing import Optional

# notes on ncurses:
#   - clear() will reset a window position, not just clear contents.  https://lists.gnu.org/archive/html/bug-ncurses/2014-01/msg00007.html
#   - erase clears the contents of an existing window, which is considerably faster
#   - clrtoeol() can clear to end of line, clrtobot() will clear the bottom of the screen
#   - writing outside of a subwindow bounds will throw an err -- see try/except guards
# other notes:
# - we probably could have done without the input window complexity, instead just redrawing the prompt on current main line
# known bugs:
# - we should stop moving the input window before we hit the max screen size via main and stop painting in position y+1,
#   which may fix other resizing errors.  scrolling back into the buffer works fine; refactor so main grabs another
#   line, then handles result_window_move
# - when window max is hit, prior input is not preserved
# - resizing from max screen size:
#       - resizing from cursor 0 to size 3 will "crash" (caught) with no input
#       - resizing from cursor 0 to cursor 1 with input will "crash" (caught)
#   this is likely related to the result expanding beyond getmaxyx() bounds. a possible solution would be adding
#   another window that simply acts as a buffer at the bottom of the screen.
RESIZE_ORD = 410 # fires in my iterm2 + tmux when resizing a window

EOF_CHORD = 4 # ^d
KEY_ENTER = 10 # \lf
KEY_Q = ord("q") # a 'q' in any position at any time will exit
KEY_BACKSPACE = 127 # ord('\x7f')
KEY_DELETE = 330

def hex_to_dec(input_value):
    """Convert input_value from hex to decimal. Accepts string returns string.

    Python makes this very easy.  The algorithm for conversion is to multiply
    each digit to the 16th power of the (0-indexed) position and sum.  e.g.

    0xBEEF
        F is 0th
        E is 1st
        E is 2nd
        F is 3rd

    (15 * 16^3) + (14 * 16^2) + (14 * 16^1) + (15 * 16^0)
    (15 * 4096) + (14 * 256) + (14 * 16) + (15 * 1) = 48879

    :param input_value: input hex string or other type coercable by int(x, 16)
    :return: result string of conversion from input hex string to dec
    """
    try:
        ret = int(input_value, 16)
    except ValueError:
        return "invalid input for base 16 conversion"
    return ret

def hex_to_dec_str(input_value):
    return str(hex_to_dec(input_value))

# type annotation because try/except value check
# instead of pythonic guardrail crash
def is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

# Htoi is a ncurses application for converting from hex to decimal
# note that an intentional chain of `if` statements are used instead of
# python 3.10's switch/match for purposes of wider availability.
class Htoi:

    def __init__(self, debug=False):
        self.debug=debug
        self.prompt = ""
        self.prompt_suffix = "htoi > "

        self.main_cursor_y = 0
        self.main_cursor_x = 0
        self.main_window: Optional["curses._CursesWindow"] = None  # window bound in main

        self.input_cursor_y = 0
        self.input_cursor_x = 0
        # type annotation used for IDE hints
        self.input_window: Optional["curses._CursesWindow"] = None  # window bound in main

        self.result_cursor_y = 0
        self.result_cursor_x = 0

        # tracks line for desired window position, not the cursor
        self.result_window_pos_y = 0
        # type annotation used for IDE hints
        self.result_window: Optional["curses._CursesWindow"] = None  # window bound in main

        self.welcome_prompt = "Please insert your hexadecimal value. \\n to convert, ^C or q to exit\n"

        self.last_input = ""
        self.current_input = ""

        # storing error in the function scope allows
        # for cheaply checking error status instead of dealing with a window object
        self.error = ""
        # once we hit the window max Y limit, we're no longer able to calculate this based on cursor position
        self.input_line_index = 0

    # subwindow moving is not supported, even though mvwin will not complain
    # ("remove  970913 feature for copying subwindow" https://ncurses.scripts.mit.edu/?p=ncurses.git;a=blobdiff;f=ANNOUNCE;h=11933c5f6d55f4f21e79e0829da3c801365977ce;hp=bbeeb8922d4724c0b184b8de901cfb0d99577bb5;hb=bfe753d2dbaed1587556f1dc89bb14066d075c8c;hpb=027ae42953e3186daed8f3882da73de48291b606)
    # if the main window has changed and will cause a violation/err on painting, we need to nuke and rebind
    # e.g. initial prompt of:
    #   prompt: "9 htoi > "
    #   idx:     012345678
    # a subwindow bound at 0 will place the cursor at idx 9
    # when prompt becomes:
    #   prompt: "10 htoi > "
    #   idx:     0123456789
    # then our subwindow will collide when trying to paint and an error will be thrown
    #
    #  manage_input_subwin tracks when our prompt length changes and manages destroying and recreating our subwin
    def manage_input_subwin(self, line_count):
        if line_count < 0:
            # we should not be here
            return

        # if power of 10, we shouldn't have any decimal
        if log10(line_count).is_integer():
            # explicitly delete our subwindow before assignment
            # a code-dive should take place to see if re-assignment does a clean GC
            del self.input_window
            self.new_input_win()
            self.debug and self.input_window.bkgd(' ', curses.color_pair(2))
            self.input_window.clear()
            self.debug and self.log("creating new subwindow of length: {}".format(len(self.prompt)))

    # create a subwindow for user input
    # this allows us to write user input and overwrite it with keypresses
    def new_input_win(self):
        main_y, _ = self.main_window.getyx()
        # we subwindow on main_y and prompt chars offset.  we track these values to
        # move the input_window dynamically along with our prompt
        self.input_window = self.main_window.subwin(1, 0, main_y , len(self.prompt))
        self.input_window.scrollok(True) # don't crash when exceeding max (e.g. X axis on small width)
        self.input_window.keypad(True) # keypad(True) to differentiate between up arrow and 'A'
        self.input_window.refresh()

    # input_window_move moves a cursor for the input window relative to main window cursor subwindow
    # self.input_window.getparyx() (get parent yx) should report where parent cursor is, but it's tracking self.input_window
    # it's possible that there's a window sync command that simplifies this whole process of tracking the main position with
    def input_window_move(self, y, x=0):
        # we want to track our input_window alongside the prompt window
        # self.input_cursor_x = self.main_cursor_x # floats to the end of the prompt
        try:
            self.debug and self.log("{} [y,x] [{}, {}]".format("moving input window position to:", y, x))
            self.input_window.mvwin(y, x)  # this line breaks going from 0 back up
        except:
            self.debug and self.log("[EXCEPTION] failed to move input window to [y,x] [{}, {}]".format(y, x))

    def input_window_replace(self, contents):
        self.debug and self.log("replacing input window with contents: {}".format(contents))
        self.input_window_wipe()
        self.input_window.addstr(contents)

    # wipe clears an input window
    def input_window_wipe(self):
        if not self.input_window:
            self.debug and self.log("attempted to clear null input_window")
            return
        self.input_window.erase()
        self.debug and self.log("cleared input window and moved to coordinates [y,x]: [{}, {}]".format(self.result_cursor_y, 0))

    # create a subwindow for error feedback and results
    def new_result_win(self):
        # single height, no columns.  transparent with no input. after we get the cursor position, we can move this.
        # if ever the result is moved to the bottom of the screen, remember to leave a row+1 for newline, a column+1 for the cursor
        self.result_window = self.main_window.subwin(1, 0, 0, 0) # moved when painting results.  initialized at 0,0
        self.result_window.keypad(True) # keypad(True) to differentiate between up arrow and 'A'
        self.result_window.leaveok(True) # leaveok prevents the cursor from jumping to window after write. see also: curses.filter() before initscr()
        self.result_window.scrollok(True)

    # result window positioning
    #
    # if we won't overflow the window, set the result window position to the "next line"
    # if we have a height of 1, allow result line to output over prompt
    #
    def result_window_move(self):

        main_max_y, _ = self.main_window.getmaxyx()

        if self.main_cursor_y + 1 < main_max_y:
            self.result_window_pos_y = self.main_cursor_y + 1
            # if max is y=2 and cursor will move to y=1, this crashes without being guarded
            # if self.max_y == 2:
            #     new_y = 1
            # current line + 1, start of line
            self.debug and self.log("{} [y,x] [{}, {}]".format("moving result window to:", self.result_window_pos_y, 0))
            try:
                self.result_window.mvwin(self.result_window_pos_y, 0)  # this line crashes when scaling up from y height=0
            except:
                self.debug and self.log("[EXCEPTION] failed to move result window to [y,x] [{}, {}]".format(self.result_window_pos_y, len(self.prompt)))
        else:
            self.result_window_pos_y = main_max_y - 1
            # this condition will be hit if the result window is moved before
            if self.result_window_pos_y < 0:
                self.result_window_pos_y = 0

            self.debug and self.log("{} [y,x] [{}, {}]".format("[max size constraint] moving result window to: ", self.result_window_pos_y , 0))
            # there will be no room for the confirmed result, but max_y -1 will keep the result within the bounds as we scale down
            try:
                self.result_window.mvwin(self.result_window_pos_y, 0)
            except:
                self.debug and self.log("[EXCEPTION] failed to move result window to [y,x] [{}, {}]".format(self.result_window_pos_y, len(self.prompt)))


    # result_window_set_invalid_input_error clears any existing error, writes a new error, and preserves the
    # window's location from the last char input
    def result_window_set_invalid_input_error(self, i, i_chr):
        self.result_window_wipe()
        self.result_window.bkgd(' ', curses.color_pair(1))
        # the result_window has been moved for us into position already by result_window_clear(
        self.error = "input not valid hexadecimal character. ord: {o} chr: {c}".format(o=i, c=i_chr)
        self.result_window.addstr(self.error)
        self.result_window.refresh()

    # result_window_wipe clears any existing result and preserves the window's last location
    # from the last char input
    def result_window_wipe(self):
        if not self.result_window:
            self.debug and self.log("attempted to clear null result_window")
            return
        self.result_window.leaveok(True)  # don't move the cursor to the result window
        # if we previously had an error, the result window will have a background used for errors
        self.result_window.bkgd(' ')
        self.result_window.erase()
        self.debug and self.log("cleared result window".format(self.result_window_pos_y, 0))
        self.result_window.refresh()

    @staticmethod
    def log(message):
        with open("debug.log", "a") as f:
            time_marker = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            f.write("[{timeMarker}] {msg}\n".format(timeMarker=time_marker, msg=message))

    def report_positions(self):
        main_max_y, main_max_x = self.main_window.getmaxyx()
        ic_my, ic_mx = self.input_window.getmaxyx()
        # max y for result_window is a function of main_max_y
        _, rw_mx = self.result_window.getmaxyx()

        # max, cursor formatted for sake of fixed width / log alignment
        self.log("{:<12} [y,x] [{}, {}] cursor: [{}, {}]".format("MAIN: max", main_max_y, main_max_x, self.main_cursor_y, self.main_cursor_x))

        self.log("{:<12} [y,x] [{}, {}] cursor: [{}, {}]".format("RESULT: max", self.result_window_pos_y , rw_mx, self.result_cursor_y, self.result_cursor_x))

        self.log("{:<12} [y,x] [{}, {}] cursor: [{}, {}] pos: [{}, {}]".format(
            "INPUT: max", ic_my, ic_mx, self.input_cursor_y, self.input_cursor_x, self.main_cursor_y, self.main_cursor_x)),


    # curses import does not include underscored name
    # type annotation used for IDE hints
    def main(self, main_window: "curses._CursesWindow") -> None:
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_GREEN)

        # main_window is bound for access to cursor and max positions
        self.main_window = main_window
        main_window.clear()
        main_window.keypad(True) # keypad(True) to differentiate between up arrow and 'A'
        main_window.scrollok(True) # don't crash when we hit the bottom of the window
        main_window.addstr(self.welcome_prompt)

        self.main_cursor_y, self.main_cursor_x = main_window.getyx()

        # set the input_line_index to where we can start accepting input
        # the input_line_index does not track with cursor as result gets painted after the prompt/input
        self.input_line_index += self.main_cursor_y
        self.prompt = "{} {}".format(self.input_line_index, self.prompt_suffix)

        # note that any addstr() will set cursor position to the following x+1 position for a given y
        main_window.addstr(self.prompt) # prompt belongs to main window, user input goes to input_window
        main_window.leaveok(True) # the user doesn't interact with main
        main_window.refresh()
        curses.curs_set(1)
        # set our initial cursor positions post writing our prompts
        self.main_cursor_y, self.main_cursor_x = main_window.getyx()

        self.new_input_win()
        self.new_result_win()

        self.debug and self.input_window.bkgd(' ', curses.color_pair(2))

        self.debug and self.log("### window initialized ###")
        while True:
            self.debug and self.log("looping for input")

            # we get the maximum positions on each loop to handle window resizing and placement
            self.main_cursor_y, self.main_cursor_x = main_window.getyx()

            # the Y coordinate will be 0 unless the contents of the input window are multiple lines
            # this is not the global position on screen
            self.input_cursor_y, self.input_cursor_x = self.input_window.getyx()

            # the Y coordinate will be 0 unless the contents of the result window are multiple lines
            # this is not the global position on screen
            self.result_cursor_y, self.result_cursor_x = self.result_window.getyx()
            self.debug and self.report_positions()

            try:
                # loop for next input
                i = self.input_window.getch()
                self.input_window.refresh()

                # ^C exits.  let ^D quit, let "q" quit
                if i == EOF_CHORD or i == KEY_Q:
                    curses.endwin()
                    return

                if i == RESIZE_ORD:
                    continue

                # if input is up allow, set user input to the last input
                # very likely the user will then backspace, edit, hit enter
                if i == curses.KEY_UP:
                    self.debug and self.log("replacing current input: {c} with last input: {p}".format(c=self.current_input, p=self.last_input))
                    # throw away whatever we have built up for current_input
                    # and replace with the last_input that was valid for conversion
                    self.current_input = self.last_input
                    # get the result window out of the way in case it's on the last return. else this will
                    # stomp on the result return
                    self.result_window_move()
                    # result not valid anymore
                    self.result_window_wipe()
                    self.input_window_replace(self.current_input)
                    self.input_window.refresh()
                    continue

                # if i == curses.KEY_LEFT:
                # input_window.move
                # handle delete + replace on current char
                # if at the beginning of input...

                # if i == curses.KEY_RIGHT:
                # input_window.move
                # handle delete + replace on current char
                # if at the end of input...

                # handle backspace
                if i in (curses.KEY_BACKSPACE, KEY_BACKSPACE, KEY_DELETE):
                    self.report_positions()
                    if len(self.current_input) == 0:
                        self.debug and self.log("no text left to delete")
                        continue

                    self.current_input = self.current_input[:-1]
                    self.input_window_replace(self.current_input)

                    # if we previously had an error, the result window will have a background used for errors
                    self.result_window_wipe()
                    self.result_window_move()
                    # if we send an empty string to addstr, we'll get back an error
                    result = ""
                    if len(self.current_input) > 0:
                        result = hex_to_dec_str(self.current_input)
                        self.result_window.addstr(0,0, result)

                    self.debug and self.log("wrote result after backspace: " + result)

                    self.result_window.refresh()
                    self.input_window.refresh()
                    continue

                # KEY_ENTER is some numeric keyboards
                # macOS sends a \lf with the <return> key
                # treat these as their numeric inputs (no ord)
                if i == curses.KEY_ENTER or i == KEY_ENTER:
                    self.result_window.leaveok(True) # needed?
                    # if we have an error, clear it out. no output needs preservation.
                    if len(self.error) > 0:
                        self.error = ""
                        # clear window contents and refresh to update it
                        self.debug and self.log("updating clearing error from result window")
                        # if we previously had an error, the result window will have a background used for errors
                        self.result_window_wipe()
                        # do not clear any other windows, this is dismissing the error only
                        continue

                    # just ignore errant or idle return presses
                    if self.current_input.strip() == "":
                        continue

                    self.input_line_index += 1
                    self.prompt = "{} {}".format(self.input_line_index, self.prompt_suffix)

                    # wipe to clear the window for main_window to write to the previously occupied space
                    self.input_window_wipe()
                    # write the input that was entered into the main_window to mimic
                    # preserving the input window. we use the input window only for active input
                    main_window.addstr(self.current_input.strip())

                    # clear over input line with a return before writing our result
                    # this is bypassing the input window
                    main_window.addstr("\n")
                    # set current input minus confirmation
                    result = hex_to_dec_str(self.current_input)

                    # on confirmation, we send the result to the main screen, not the live-updating results window
                    # we do this to advance the "cursor" of window anchoring
                    # e.g.
                    #  [ main: >>> ] [ user input ]
                    #  [ live updating results]
                    # <enter>
                    #  [ main: >>> ] [ user input ]
                    #  [ main: result ]
                    #  [ main: >>> ] [ user input ]
                    #  [ live updating results]
                    main_window.addstr(result, curses.A_STANDOUT)

                    # with output provided, now store last result for recall
                    self.last_input = self.current_input
                    self.current_input = ""

                    # redraw prompt by moving main window line
                    main_window.addstr("\n")
                    main_window.addstr(self.prompt)
                    # update main cursor location, which is used to calculate where to draw our input box
                    self.main_cursor_y, self.main_cursor_x = main_window.getyx()
                    self.debug and self.report_positions()
                    # main_window.refresh() to redraw our prompt for input
                    main_window.refresh()

                    # now move input box, clearing out any contents first
                    self.manage_input_subwin(self.input_line_index)
                    # this wipe clears any content left in the window post-move,
                    # such as text likely shifted down leftover from our prior input space that was written into by main_window
                    self.input_window_wipe()
                    self.input_window_move(self.main_cursor_y, len(self.prompt))
                    self.input_window.refresh()
                    self.debug and self.log("result recorded, input window adjusted for new input")
                    continue

                # else, we have user input pending conversion
                # convert ordinal to Unicode code point
                i_chr = chr(i)

                if not is_hex(i_chr):
                    self.result_window_move()
                    self.result_window_set_invalid_input_error(i, i_chr)
                else:
                    # if we previously had an error, the result window will have a background used for errors
                    if len(self.error) > 0:
                        self.error = ""
                        self.result_window_wipe()

                    # output to prompt line and add user input to existing current_input
                    self.current_input += i_chr
                    self.input_window.addstr(i_chr)

                    # move the result window to make sure we're not stomping on main's output
                    # then clean our current output buffer
                    self.result_window_move()
                    self.result_window_wipe()

                    result = hex_to_dec_str(self.current_input)
                    self.result_window.addstr(hex_to_dec_str(self.current_input))
                    self.debug and self.log("wrote result: " + result)
                    # self.result_window.refresh() required to paint real-time conversion result
                    self.result_window.refresh()

            # catch ^c and EOF, clean exit
            except (KeyboardInterrupt, EOFError):
                curses.endwin()
                print("exception caught")
                return

        # get next keypress
        stdscr.getkey()


    # check clear usage on input window, compare against old main setup
    # if old main setup didn't clear() that would account for line jumping
    # we then want input box to stay on the same line as prompt
    # result box should be after input/prompt box combo


if __name__ == "__main__":
    # minimal imports until we know the runtime mode
    import argparse

    parser = argparse.ArgumentParser("htoi")
    parser.add_argument("--debug", help="enable debug logging and visual indicators in interactive mode", action='store_true')
    parser.add_argument("stdin_data", help="position argument to convert, skipping interactive mode", action="store", type=str, nargs="?")
    args = parser.parse_args()

    # note for modification
    # if using zsh or fsh and you see an inverse+bold % at the end of output
    # a "partial line" was written or output without a newline

    # if we received positional args
    # arguments are already treated as strings for input
    if args.stdin_data and len(args.stdin_data) > 0:
        print(hex_to_dec(args.stdin_data))
    else:
        htoi = Htoi(debug=args.debug)

        try:
            # input grouping is kept separate for sake of run speed for non-interactive mode
            import curses
            from math import log10 # only required in interactive mode for line count
            from sys import exit # for setting exit code when interactive mode throws an uncaught exception

            # curses is imported to support up arrow input
            stdscr = curses.initscr()
            curses.start_color()
            stdscr.keypad(True) # detect special chars like key-up, otherwise key-up looks like 'A'
            # wrapper handles noecho, cbreak, keypad
            curses.wrapper(htoi.main)
        except curses.error as e:
            if htoi.debug:
                import traceback
                htoi.log(traceback.format_exc())
                raise e

            exception_summary = "Could not initialize window: {e_str}".format(e_str=e)
            print(exception_summary)
            exit(1)
