class Message:
    def __init__(self):
        self.RESET = '\033[0m'
        self.RED = '\033[31m'
        self.GREEN = '\033[32m'
        self.YELLOW = '\033[33m'
        self.WHITE = '\033[37m'
        self.BOLD_RED = '\033[1;31m'
        self.BOLD_GREEN = '\033[1;32m'
        self.BOLD_YELLOW = '\033[1;33m'
        self.BG_RED = '\033[41m'
        self.BG_GREEN = '\033[42m'
        self.BG_YELLOW = '\033[43m'

    def info(self, text):
        print(f"{self.WHITE}{text}{self.RESET}")

    def error(self, text):
        print(f"{self.RED}{text}{self.RESET}")

    def warning(self, text):
        print(f"{self.YELLOW}{text}{self.RESET}")

    def success(self, text):
        print(f"{self.GREEN}{text}{self.RESET}")
