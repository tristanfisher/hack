#!/usr/bin/env python3
from datetime import datetime, timezone

# todo: split output across multiple lines if overflowing in x dimension

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
        self.prompt = "htoi > "
        self.max_y = 0
        self.max_x = 0

        self.cursor_y = 0
        self.cursor_x = 0

        self.welcome_prompt = "Please insert your hexadecimal value. \\n to convert, ^C or q to exit\n"

        self.last_input = ""
        self.current_input = ""

        # storing error in the function scope allows
        # for cheaply checking error status instead of dealing with a window object
        self.error = ""

    @staticmethod
    def log(message):
        with open("debug.log", "a") as f:
            time_marker = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            f.write("[{timeMarker}] {msg}\n".format(timeMarker=time_marker, msg=message))

    # curses import does not include underscored name
    # type annotation used for IDE hints
    def main(self, main_window: "curses._CursesWindow") -> None:
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_WHITE)
        # block cursor

        main_window.clear()
        main_window.scrollok(True) # don't crash when we hit the bottom of the window
        main_window.addstr(self.welcome_prompt)
        main_window.addstr(self.prompt)
        curses.curs_set(1)

        EOF_CHORD = 4
        ENTER_KEY = 10 # \lf
        RESIZE_ORD = 410 # fires in my iterm2 + tmux when resizing a window
        Q_KEY = ord("q") # a 'q' in any position at any time will exit

        # create a subwindow for error feedback
        # single height, no columns.  transparent with no input. after we get the cursor position, we can move this.
        # if ever the result is moved to the bottom of the screen, remember to leave a row+1 for newline, a column+1 for the cursor
        result_window = main_window.subwin(1, 0, 0, 0)
        result_window.leaveok(True) # leaveok prevents the cursor from jumping to our error window. see also: curses.filter() before initscr()
        result_window.scrollok(True)
        # note that any addstr will set cursor position to the following x+1 position for a given y
        while True:

            # we get the maximum positions on each loop to handle window resizing and placement
            self.cursor_y, self.cursor_x = main_window.getyx()
            self.max_y, self.max_x = main_window.getmaxyx()
            # max, cursor formatted for sake of fixed width / log alignment
            self.debug and self.log("{:<7} [y,x] [{}, {}]".format("max", self.max_y, self.max_x))
            self.debug and self.log("{:<7} [y,x] [{}, {}]".format("cursor", self.cursor_y, self.cursor_x))

            # todo: resizing out of 0 crashes this

            # remote window positioning
            #
            # if we won't overflow the window, set the result window position to the "next line"
            # if we have a height of 1, allow result line to output over prompt


            # todo: if cursor and max did not change, we do not need to result_window.mvwin
            if self.cursor_y + 1 < self.max_y:
                # current line + 1, start of line
                self.debug and self.log("{} [y,x] [{}, {}]".format("moving result window to:", self.cursor_y + 1, 0))

                result_window.mvwin(self.cursor_y + 1, 0)  # this line breaks going from 0 back up
            else:
                self.debug and self.log("{} [y,x] [{}, {}]".format("moving result window to: ", self.max_y -1, 0))
                # there will be no room for the confirmed result, but self-max_y -1 will keep the result
                # within the bounds as we scale down
                result_window.mvwin(self.max_y -1, 0)

            # scaling up on a virtual terminal breaks

            try:
                # loop for next input
                i = main_window.getch()

                # ^C cleanly exits.  let ^D quit, let "q" quit
                if i == EOF_CHORD or i == Q_KEY:
                    return

                if i == RESIZE_ORD:
                    continue

                # if input is up allow, set user input to the last input
                # very likely the user will then backspace, edit, hit enter
                if i == curses.KEY_UP:

                    # throw away whatever we have built up for current_input
                    # and replace with the last_input that was valid for conversion
                    current_input = self.last_input
                    # update screen?
                    # curses.doupdate? refresh?
                    continue

                # handle left/right
                # highlight char at position for replacement
                # if i == curses.KEY_LEFT:
                # if at the beginning of input
                # main_window.move

                # if i == curses.KEY_RIGHT:
                # main_window.move
                # if at the end of input...

                # handle delete on current char
                #

                # handle backspace
                # if i == curses.KEY_BACKSPACE

                # KEY_ENTER is some numeric keyboards
                # macos sends a \lf with the <return> key
                # treat these as their numeric inputs (no ord)
                if i == curses.KEY_ENTER or i == ENTER_KEY:
                    # if we have an error, clear it out
                    if len(self.error) > 0:
                        self.error = ""
                        # clear window contents and refresh to update it
                        self.log("updating error window")
                        result_window.clear()
                        result_window.refresh()
                        main_window.refresh()
                        # now continue -- this is dismissing the error
                        continue

                    # just ignore errant or idle return presses
                    if self.current_input.strip() == "":
                        continue

                    # clear input line with a return before writing our result
                    main_window.addstr("\n")
                    # set current input minus confirmation
                    result = hex_to_dec_str(self.current_input)
                    # on confirmation, we send the result to the main screen, not the live-updating results window
                    main_window.addstr(result, curses.A_STANDOUT)

                    # with output provided, now store last result
                    # for recall
                    self.last_input = self.current_input
                    self.current_input = ""

                    # redraw prompt
                    main_window.addstr("\n")
                    main_window.addstr(self.prompt)

                    continue

                # else, we have user input pending conversion
                # convert ordinal to Unicode code point
                i_chr = chr(i)

                if not is_hex(i_chr):
                    result_window.bkgd(' ', curses.color_pair(1))

                    # we specifically do not clear out the current input or change the prompt
                    # the result_window has been moved for us into position already
                    self.error = "input not valid hexadecimal character. ord: {o} chr: {c}".format(o=i, c=i_chr)
                    result_window.clear()
                    result_window.addstr(0, 0, self.error)
                    result_window.refresh()
                    # enter/confirmation knows how to clear errors
                else:
                    self.error = ""
                    # if we previously had an error, the result window will have a background used for errors
                    result_window.bkgd(' ')
                    result_window.clear()
                    result_window.refresh()

                    # output to prompt line and add user input to existing current_input
                    main_window.addstr(i_chr)
                    self.current_input += i_chr

                    # show hex for current input
                    # when user hits save, this result will get preserved in the main window,
                    # but for now, we live update the workspace
                    result = hex_to_dec_str(self.current_input)
                    result_window.addstr(0,0, result)
                    result_window.refresh()

            # catch ^c and ^d, clean exit
            except (KeyboardInterrupt, EOFError):
                print("exception caught")
                return

        # get next keypress
        main_window.getkey()


if __name__ == "__main__":
    import sys


    # TODO: take in flag for debug to dump traces and other detail
    debugSetting = True
    htoi = Htoi(debug=debugSetting)


    # note for modification
    # if using zsh or fsh and you see an inverse+bold % at the end of output
    # a "partial line" was written or output without a newline

    # if we received positional args
    # arguments are already treated as strings for input
    if len(sys.argv) > 1:
        print(hex_to_dec(sys.argv[1]))
    else:
        try:
            import curses
            # curses is imported to support up arrow input
            stdscr = curses.initscr()
            curses.start_color()

            # wrapper handles noecho, cbreak, keypad
            curses.wrapper(htoi.main)
        except curses.error as e:
            if htoi.debug:
                raise e

            exception_summary = "Could not initialize window: {e_str}".format(e_str=e)
            print(exception_summary)
            sys.exit(1)
