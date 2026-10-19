import os
import sys

from swirl.__main__ import main

try:
    sys.exit(main())
except BrokenPipeError:  # output piped into head/less that closed early
    os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    sys.exit(0)
