from pydantic_settings import BaseSettings

from mountaineer.config import ConfigBase


def test_merge_configs():
    """
    Ensure that we can merge two configurations together, both
    during type checking and during runtime.

    """

    class Settings1(BaseSettings):
        ABC: str

    class Settings2(BaseSettings):
        DEF: str

    class Config(ConfigBase, Settings1, Settings2):
        pass

    config = Config(ABC="abc", DEF="def")
    assert config.ABC == "abc"
    assert config.DEF == "def"
