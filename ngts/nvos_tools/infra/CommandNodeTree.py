
class CommandNode:
    def __init__(self):
        self.sub_command = {}
        self.is_end_of_command = False


class CommandNodeTree:
    def __init__(self):
        self.root = CommandNode()

    def build_tree(self, command_str):
        """
        Insert command node corresponding to a command string
        :param  command_str :   Command string
        :return None
        """
        command_node = self.root
        command_components = command_str.split()
        for component in command_components:
            if component not in command_node.sub_command:
                command_node.sub_command[component] = CommandNode()
            command_node = command_node.sub_command[component]
        command_node.is_end_of_command = True

    def search_command(self, command):
        """
        Search a command in the command tree
        :param  command :   Command string
        :return bool    :   True if the command exists, otherwise False
        """
        command_node = self.root
        command_components = command.split()
        for component in command_components:
            if component not in command_node.sub_command:
                return False
            command_node = command_node.sub_command[component]
        return command_node.is_end_of_command

    def find_paths(self, start_command_node=None):
        """
        Finds all possible commands
        :param  start_command_node: starting node to get commands
        :return command_tree_str:   list of strings, where each string is a full command path
        """
        if start_command_node is None:
            start_command_node = self.root

        paths = []
        self._find_paths_recursive(start_command_node, [], paths)
        return [" ".join(path) for path in paths]

    def _find_paths_recursive(self, node, current_path, all_paths):
        """
        Recursive helper function to find all commands from a command string
        """
        if node.is_end_of_command:
            all_paths.append(list(current_path))

        for key, subcommand in node.sub_command.items():
            current_path.append(key)
            self._find_paths_recursive(subcommand, current_path, all_paths)
            current_path.pop()  # Backtrack

    def get_node_by_command(self, command_str):
        """
        Get the Command Node corresponding to a given command path string
        :param  command_str:    Command path string
        :return command_node:   Command Node if the path exists, otherwise None
        """

        command_node = self.root
        command_components = command_str.split()

        for component in command_components:
            if component in command_node.sub_command:
                command_node = command_node.sub_command[component]
            else:
                return None  # Path part not found

        return command_node
