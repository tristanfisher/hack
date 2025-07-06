#!/usr/bin/env python3

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
    return str(int(input_value, 16))

if __name__ == "__main__":
    import sys

    # if we received positional args
    if len(sys.argv) > 1:
        print(hex_to_dec(sys.argv[1]))
    else:
        print("Please insert your hexidecimal value. \\n to convert, ^C or empty input to exit: ")
        while 1:
            i = input("> ")
            if not i:
                exit(0)
            try:
                print(hex_to_dec(i))
            except ValueError:
                print("input not hexadecimal")