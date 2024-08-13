class LinuxCmdBuilderTool:
    def __init__(self, base_cmd=""):
        self.command = base_cmd

    def cat(self, filename):
        """
            Concatenate and print files
            cat secrets.txt
        """
        self.command += f'cat {filename}'
        return self

    def grep(self, pattern):
        """
            Utility to search based on pattern
            grep "api_key"
        """
        self.command += f' | grep "{pattern}"'
        return self

    def grep_regex(self, pattern):
        """
            Utility to search based on regex pattern
            grep -E "error|err|ERR"
        """
        return self.grep(f" -E {pattern}")

    def trim(self, separator=" "):
        """
            Deletes or substitutes specified characters
            -s Squeeze multiple occurrences of the characters listed in the last operand
            Example:
            echo "This                tool       is     awesome" | tr -s " " -> "This tool is awesome"
        """
        self.command += f' | tr -s "{separator}"'
        return self

    def cut(self, column_number, separator=" "):
        """
            Cuts out selected portion of each line based on provided chars.
            -d flag specifies delimiter, should be used with -f.
            -f The list specifies fields, separated in the input by the field delimiter character. Starts from 1
                -f2,4 means second and fourth field should be extracted.
            Example:
            echo "All your inputs belong to me" | cut -d " " -f2 -> "your"
        """
        self.command += f' | cut -d "{separator}" -f{column_number}'
        return self

    def awk_print(self, column_numbers_comma):
        """
            It's pattern scanning programming language.
            In this case just returns the column you need.
            echo "This                tool       is     awesome" | awk '{print $2, $4}' -> "tool awesome"
        """
        self.command += f" | awk '{{print ${column_numbers_comma}}}'"
        return self

    def column(self, column_number, separator=" "):
        return self.trim(separator).cut(column_number, separator)

    def build(self):
        return self.command.strip()
