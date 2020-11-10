"""
Agent documentation goes here.
"""

__docformat__ = 'reStructuredText'

import logging
import sys
from volttron.platform.agent import utils
from volttron.platform.vip.agent import Agent, Core, RPC
from pprint import pprint


_log = logging.getLogger(__name__)
utils.setup_logging()
__version__ = "0.1"


def tester(config_path, **kwargs):
    """Parses the Agent configuration and returns an instance of
    the agent created using that configuration.

    :param config_path: Path to a configuration file.

    :type config_path: str
    :returns: Tester
    :rtype: Tester
    """
    try:
        config = utils.load_config(config_path)
    except Exception:
        config = {}

    if not config:
        _log.info("Using Agent defaults for starting configuration.")

    historian_vip = config.get('historian_vip', "platform.historian")
    output_path = config.get('output', "historian_output")

    return Tester(historian_vip, output_path,  **kwargs)


class Tester(Agent):
    """
    Document agent constructor here.
    """

    def __init__(self,
                 historian_vip="platform.historian",
                 output_path="historian_output",
                 **kwargs):
        super(Tester, self).__init__(**kwargs)
        _log.debug("vip_identity: " + self.core.identity)

        self.historian_vip = historian_vip
        self.output_path = output_path

        self.default_config = {"historian_vip": historian_vip,
                               "output": output_path}


        # Set a default configuration to ensure that self.configure is called immediately to setup
        # the agent.
        self.vip.config.set_default("config", self.default_config)
        # Hook self.configure up to changes to the configuration file "config".
        self.vip.config.subscribe(self.configure, actions=["NEW", "UPDATE"], pattern="config")

    def configure(self, config_name, action, contents):
        """
        Called after the Agent has connected to the message bus. If a configuration exists at startup
        this will be called before onstart.

        Is called every time the configuration in the store changes.
        """
        config = self.default_config.copy()
        config.update(contents)

        _log.debug("Configuring Agent")

        try:
            historian_vip = config["historian_vip"]
            output_path = config["output"]
        except ValueError as e:
            _log.error("ERROR PROCESSING CONFIGURATION: {}".format(e))
            return

        self.historian_vip = historian_vip
        self.output_path = output_path

    @Core.receiver("onstart")
    def onstart(self, sender, **kwargs):
        """
        This is method is called once the Agent has successfully connected to the platform.
        This is a good place to setup subscriptions if they are not dynamic or
        do any other startup activities that require a connection to the message bus.
        Called after any configurations methods that are called at startup.

        Usually not needed if using the configuration store.
        """

        result1 = self.vip.rpc.call(
            self.historian_vip,
            "get_topics_by_pattern",
            ".*OutsideAirTemperature.*").get(timeout=10)

        result2 = self.vip.rpc.call(
            self.historian_vip,
            "query",
            topic="fake-campus/fake-building/fake-device/EKG",
            count=5,
            order="FIRST_TO_LAST").get(timeout=10)

        # pretty print the result to file
        with open(self.output_path, 'w') as out:
            out.write("Topics that matched pattern .*OutsideAirTemperature.* are:\n\n")
            pprint(result1, stream=out)
            out.write("\n\nData from topic fake-campus/fake-building/fake-device/EKG:\n\n")
            pprint(result2, stream=out)

    @Core.receiver("onstop")
    def onstop(self, sender, **kwargs):
        """
        This method is called when the Agent is about to shutdown, but before it disconnects from
        the message bus.
        """
        pass

    @RPC.export
    def rpc_method(self, arg1, arg2, kwarg1=None, kwarg2=None):
        """
        RPC method

        May be called from another agent via self.core.rpc.call """
        return self.setting1 + arg1 - arg2

def main():
    """Main method called to start the agent."""
    utils.vip_main(tester, 
                   version=__version__)


if __name__ == '__main__':
    # Entry point for script
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
