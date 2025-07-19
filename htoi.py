#!/usr/bin/env python3

# todo: if window size is 3, conditionally don't use the result window, only feedback

RESIZE_ORD = 410 # fires in my iterm2 + tmux when resizing a window

EOF_CHORD = 4 # ^d
KEY_ENTER = 10 # \lf
KEY_Q = ord("q") # a 'q' in any position at any time will exit
KEY_BACKSPACE = 127 # ord('\x7f')
KEY_DELETE = 330

# type annotation because try/except value check
# instead of pythonic guardrail crash
def is_hex(s: str) -> bool:
    try:
        int(s, 16)
        return True
    except ValueError:
        return False

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
    :return: result string of conversion from input hex string to dec or -1 if not valid hex
    """
    try:
        ret = int(input_value, 16)
    except ValueError:
        return -1
    return ret

def hex_to_dec_str(input_value):
    return str(hex_to_dec(input_value))

# Htoi is a ncurses application for converting from hex to decimal
# note that an intentional chain of `if` statements are used instead of
# python 3.10's switch/match for purposes of wider availability.
#
# a rough layout sketch is:
# [htoi > ][ input window ]
# [ result_buffer window ]
# [ history window ]
#
# "htoi > " is provided by the main window
# input window is separate for ease of clearing
# feedback_window window is used for per-char result updating
# history window is reverse-order list rendering (most recent at top)
#
class Htoi:
    def __init__(self, debug=False):
        self.debug=debug
        self.bg_red = 1
        self.bg_green = 2
        self.bg_blue = 3

        self.prompt = "htoi > "

        self.main_window: Optional["curses._CursesWindow"] = None  # window bound in main
        self.input_window: Optional["curses._CursesWindow"] = None  # window bound in main
        self.feedback_window: Optional["curses._CursesWindow"] = None  # window bound in main
        self.history_window: Optional["curses._CursesWindow"] = None  # window bound in main

        self.feedback_window_start_y = 1
        self.history_window_start_y = 2

        self.last_input = ""
        self.current_input = ""
        # storing error in the function scope allows
        # for cheaply checking error status instead of dealing with a window object
        self.error = ""


    def input_window_new(self):
        main_y, main_x = self.main_window.getyx()
        # begin immediately following main win, with 1 line, 0 columns
        self.input_window = self.main_window.subwin(1, 0, main_y, main_x)
        self.input_window.scrollok(True) # while we don't expect to draw a newline, we could wrap on the X axis
        self.input_window.keypad(True) # keypad(True) to differentiate between up arrow and 'A'
        self.debug and self.input_window.bkgd(' ', curses.color_pair(self.bg_green))

    def input_window_replace(self, contents):
        self.debug and self.log("replacing input window with contents: {}".format(contents))
        self.input_window.erase()
        self.input_window.addstr(contents)

    def feedback_window_new(self):
        # main_y, main_x = self.main_window.getyx()
        # placed under prompt, not moved, only cleared/re-used
        # one line, one column, at y=feedback_window_start_y, x=0
        self.feedback_window = self.main_window.subwin(1, 0, self.feedback_window_start_y, 0)
        self.feedback_window.scrollok(True) # result could overflow in X dimension
        self.feedback_window.leaveok(True) # leaveok prevents the cursor from jumping to window after write. see also: curses.filter() before initscr()
        self.debug and self.feedback_window.bkgd(' ', curses.color_pair(self.bg_red))

    def history_window_new(self):
        # start new window below feedback window, with no defined column max so we don't have to resize
        # no count of lines is specified, with the starting point being after our feedback window
        self.history_window = self.main_window.subwin(self.history_window_start_y, 0)
        self.history_window.scrollok(True)
        self.history_window.leaveok(True)
        self.debug and self.history_window.bkgd(' ', curses.color_pair(self.bg_blue))


    @staticmethod
    def log(message):
        with open("debug.log", "a") as f:
            time_marker = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            f.write("[{timeMarker}] {msg}\n".format(timeMarker=time_marker, msg=message))

    # curses import does not include underscored name
    # type annotation used for IDE hints
    def main(self, main_window: "curses._CursesWindow") -> None:
        # with window having been init, we can no define new background
        curses.init_pair(self.bg_red, curses.COLOR_BLACK, curses.COLOR_RED)
        curses.init_pair(self.bg_green, curses.COLOR_BLACK, curses.COLOR_GREEN)
        curses.init_pair(self.bg_blue, curses.COLOR_BLACK, curses.COLOR_BLUE)
        curses.curs_set(1)  # visible cursor

        # main_window is bound for access to cursor and max positions
        self.main_window = main_window
        main_window.clear()
        main_window.keypad(True) # keypad(True) to differentiate between up arrow and 'A'
        main_window.scrollok(True) # don't crash when we hit the bottom of the window
        main_window.addstr(self.prompt)
        main_window.leaveok(True)
        main_window.refresh()

        self.input_window_new()
        self.feedback_window_new()
        self.history_window_new()

        self.feedback_window.refresh()
        self.history_window.refresh()
        self.input_window.refresh()

        self.debug and self.log("### window initialized ###")
        while True:
            self.debug and self.log("looping for input")

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
                    # if no previous input, just continue after clearing any errors
                    if not self.last_input:
                        self.feedback_window.erase()
                        self.feedback_window.refresh()
                        continue

                    self.debug and self.log("replacing current input: {c} with last input: {p}".format(c=self.current_input, p=self.last_input))
                    # throw away whatever we have built up for current_input
                    # and replace with the last_input that was valid for conversion

                    self.current_input = self.last_input
                    # feedback for input not relevant anymore
                    self.feedback_window.erase()
                    self.feedback_window.addstr(hex_to_dec_str(self.current_input), curses.A_STANDOUT)
                    self.feedback_window.refresh()

                    # refresh input_window last so cursor returns to user input
                    self.input_window.erase()
                    self.input_window.addstr(self.current_input)
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
                    if len(self.current_input) == 0:
                        self.debug and self.log("no text left to delete")
                        continue

                    self.current_input = self.current_input[:-1]
                    self.input_window_replace(self.current_input)

                    # if we previously had an error, the result window will have a background used for errors
                    self.feedback_window.erase()
                    # if we send an empty string to addstr, we'll get back an error
                    result = ""
                    if len(self.current_input) > 0:
                        result = hex_to_dec_str(self.current_input)
                        self.feedback_window.addstr(result, curses.A_STANDOUT)

                    self.debug and self.log("wrote result after backspace: " + result)

                    self.feedback_window.refresh()
                    self.input_window.refresh()
                    continue

                # KEY_ENTER is some numeric keyboards
                # macOS sends a \lf with the <return> key
                # treat these as their numeric inputs (no ord)
                if i == curses.KEY_ENTER or i == KEY_ENTER:
                    if len(self.error) > 0:
                        self.error = ""
                        # clear window contents and refresh to update it
                        self.debug and self.log("updating clearing error from result window")
                        # if we previously had an error, the result window will have a background used for errors
                        self.feedback_window.bkgd(' ')
                        # reset expected debug decoration if necessary
                        self.debug and self.feedback_window.bkgd(' ', curses.color_pair(self.bg_red))
                        self.feedback_window.erase()
                        # do not clear any other windows, this is dismissing the error only
                        self.feedback_window.refresh()
                        # refresh input_window to set cursor
                        self.input_window.refresh()
                        continue

                    # just ignore errant or idle return presses
                    self.current_input = self.current_input.strip()
                    if self.current_input == "":
                        continue

                    result = hex_to_dec_str(self.current_input)
                    result_history_output = "{} => {}\n".format(self.current_input, result)

                    self.feedback_window.erase()
                    self.input_window.erase()
                    self.history_window.addstr(result_history_output)

                    # with output provided, now store last result for recall
                    self.last_input = self.current_input
                    self.current_input = ""

                    self.feedback_window.refresh()
                    self.history_window.refresh()
                    # refresh input_window last so cursor returns to user input
                    self.input_window.refresh()
                    continue

                # else, we have user input pending conversion
                # convert ordinal to Unicode code point
                i_chr = chr(i)

                # we check each char for being valid hex
                if not is_hex(i_chr):
                    # self.error stored for checking what we sent to the screen on the next loop through
                    self.error = "input not valid hexadecimal character. ord: {o} chr: {c}".format(o=i, c=i_chr)
                    self.feedback_window.erase()
                    self.feedback_window.addstr(self.error, curses.A_STANDOUT)
                    self.feedback_window.refresh()
                    continue

                if len(self.error) > 0:
                    # clear out error tracking, but hold off on refresh or writing
                    # as we're going to refresh this window later anyway when we write
                    # the updated result for current input
                    self.error = ""

                self.current_input += i_chr
                self.input_window.addstr(i_chr)

                result = hex_to_dec_str(self.current_input)
                self.feedback_window.erase()
                self.feedback_window.addstr(result, curses.A_STANDOUT)
                self.feedback_window.refresh()


            # catch ^c and EOF, clean exit
            except (KeyboardInterrupt, EOFError):
                curses.endwin()
                print("exception caught")
                return


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
            from datetime import datetime, timezone
            from typing import Optional
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
