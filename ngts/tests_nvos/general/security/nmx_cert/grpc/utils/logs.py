import logging
# Create standalone_logger
standalone_logger = logging.getLogger()
standalone_logger.setLevel(logging.INFO)

# Create console handler and set level to info
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s\t[%(levelname)s]\t%(message)s')

# Add formatter to ch
ch.setFormatter(formatter)

# Add ch to standalone_logger
standalone_logger.addHandler(ch)
