import logging.handlers
import os
import logging

def setup_logging(
    logger_name : str = "dockmaster",
    log_level: str | None = None, 
    log_file: str | None = None
):
    if not log_level:
        # Default log level from environment variable, default to INFO
        log_level = "INFO"

    # Create a logger
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)

    # Create formatters
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # (optional) File handler 
    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger

#Override and grab the fastapi server logger
def setup_uvicorn_logger(log_level: str | None = None):
    """Hack to get the logs working as i want them"""
    if log_level is None:
        log_level = "INFO"
    logger = logging.getLogger('uvicorn.error')
    logger.setLevel(log_level)
    return logger



# Create the default logger instance
logger = setup_logging(
    logger_name = "dockmaster",
    log_level = "INFO", 
    log_file = None
)