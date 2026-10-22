import logging
import sys

class ColoredFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\033[92m",
        "WARNING": "\033[93m",
        "ERROR": "\033[91m",
        "TIME": "\033[96m",
        "RESET": "\033[0m"
    }

    def format(self, record):
        level_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset_color = self.COLORS["RESET"]
        time_color = self.COLORS["TIME"]
        record.asctime = self.formatTime(record, datefmt="%Y-%m-%d %I:%M:%S %p")
        return f"{time_color}{record.asctime}{reset_color} | {level_color}{record.levelname}{reset_color} | {record.getMessage()}"

logger = logging.getLogger()
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(ColoredFormatter())
logger.addHandler(handler)
logger.propagate = False

logger.info('[+] Logger File Excecuted !')
