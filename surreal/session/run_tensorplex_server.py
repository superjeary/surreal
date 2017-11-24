"""
Only 1 command line arg: JSON string of session_config
"""
import os
import sys
import json
from tensorplex import TensorplexServer
from surreal.session.config import Config
from surreal.session.tensorplex_adapter import (
    AGENT_GROUP_NAME, NONAGENT_GROUP_NAME
)
from surreal.session.default_configs import BASE_SESSION_CONFIG


config = Config(json.loads(sys.argv[1]))
config.extend(BASE_SESSION_CONFIG)
folder = config.folder
config = config.tensorplex


tensorplex = TensorplexServer(
    folder,
    normal_groups=[NONAGENT_GROUP_NAME],
    indexed_groups=[AGENT_GROUP_NAME],
    index_bin_sizes=[config.agent_bin_size],
)
tensorplex.start_server(
    host=config.host,
    port=config.port,
)