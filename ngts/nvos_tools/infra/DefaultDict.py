from collections import defaultdict


class DefaultDict(defaultdict):
    """
    collections.defaultdict is a class that inherits the builtin dict.

    with builtin dict - when trying to access a key which doesn't exist, exception is raised.
    with collections.defaultdict - it adds the desired key with a default value, which the user should specify
        when initializing the defaultdict object.

    however, with collections.defaultdict, the default value can only be a const and can't be based on the key.

    with DefaultDict, can set the default value to depend on the key.

    Example:
        dd = DefaultDict(lambda k: "hello to " + k).
        --> assuming the keys are strings, every access to a new key will generate "hello to <new key>"
    """

    def __missing__(self, key):
        self[key] = value = self.default_factory(key)
        return value
