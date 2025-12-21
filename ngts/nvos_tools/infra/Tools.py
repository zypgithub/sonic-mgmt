from .PollingTool import PollingTool
from .RandomizationTool import RandomizationTool
from .SendCommandTool import SendCommandTool
from .OutputParsingTool import OutputParsingTool
from .TrafficGeneratorTool import TrafficGeneratorTool
from .TrafficValidatorTool import TrafficValidatorTool
from .ValidationTool import ValidationTool
from .IpTool import IpTool
from .ConfigTool import ConfigTool
from .SonicMgmtContainer import SonicMgmtContainer
from .HostMethods import HostMethods
from .DatabaseTool import DatabaseTool
from .FilesTool import FilesTool
from .InterfaceConfigurationTool import InterfaceConfigurationTool


class Tools:
    PollingTool = PollingTool()
    RandomizationTool = RandomizationTool()
    SendCommandTool = SendCommandTool()
    OutputParsingTool = OutputParsingTool()
    TrafficGeneratorTool = TrafficGeneratorTool()
    TrafficValidatorTool = TrafficValidatorTool()
    ValidationTool = ValidationTool()
    IpTool = IpTool()
    ConfigTool = ConfigTool()
    SonicMgmtContainer = SonicMgmtContainer()
    HostMethods = HostMethods()
    DatabaseTool = DatabaseTool()
    FilesTool = FilesTool()
    InterfaceConfigurationTool = InterfaceConfigurationTool()
