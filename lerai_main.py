import sys
import os

import logging
logging.basicConfig(filename='lerai.log', level=logging.INFO)

# Add the 'lerai' subdirectory to the Python path
# to ensure that modules inside 'lerai' can be imported.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'lerai')))

from lerai_main import lerai_main

if __name__ == "__main__":
    lerai_main()

    

