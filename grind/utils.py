class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"

    @staticmethod
    def header(text: str) -> str:
        return f"{Color.BOLD}{Color.CYAN}{text}{Color.RESET}"

    @staticmethod
    def success(text: str) -> str:
        return f"{Color.GREEN}{text}{Color.RESET}"

    @staticmethod
    def error(text: str) -> str:
        return f"{Color.RED}{text}{Color.RESET}"

    @staticmethod
    def warning(text: str) -> str:
        return f"{Color.YELLOW}{text}{Color.RESET}"

    @staticmethod
    def info(text: str) -> str:
        return f"{Color.BLUE}{text}{Color.RESET}"

    @staticmethod
    def dim(text: str) -> str:
        return f"{Color.DIM}{text}{Color.RESET}"

    @staticmethod
    def bold(text: str) -> str:
        return f"{Color.BOLD}{text}{Color.RESET}"

    @staticmethod
    def model_badge(model: str) -> str:
        colors = {
            "opus": Color.MAGENTA,
            "sonnet": Color.BLUE,
            "haiku": Color.CYAN,
        }
        color = colors.get(model, Color.WHITE)
        return f"{color}{Color.BOLD}[{model}]{Color.RESET}"
