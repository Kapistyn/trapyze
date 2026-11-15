import os

# Tests never ask GitHub for a newer traPYze.
os.environ["TRAPYZE_NO_UPDATE_CHECK"] = "1"
