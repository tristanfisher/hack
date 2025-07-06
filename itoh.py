#!/usr/bin/env python3

def dec_to_hex(input_value):
    """Convert input_value from decimal to hex. Accepts string returns string.

    :param input_value: input decimal string or other type coercable by hex()
    :return: result string of conversion from input dec to hex
    """
    return hex(int(input_value))

if __name__ == "__main__":
    import sys

    # if we received positional args
    if len(sys.argv) > 1:
        print(dec_to_hex(sys.argv[1]))
    else:
        # consider interactive input
        print("Please insert your decimal value. \\n to convert, ^C or empty input to exit: ")
        while 1:
            i = input("> ")
            if not i:
                exit(0)
            try:
                print(dec_to_hex(i))
            except ValueError:
                print("input not integer")

