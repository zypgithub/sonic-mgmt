import os
import re


def parse_escape_docker_env_secrets(mars_docker_env_secrets):
    """"
    Input: String of env vars in the format: "--env VAR1=value1 --env VAR2=value2 ...."
    Parse the docker env secrets and escape the single quotes.
    returns the shell friendly array of env vars:
    [
        "VAR1=value1",
        "VAR2=value2",
        ...
    ]
    """
    regex = r"[\w|_]+=[|\'\w\d$!-\.\/\-:~\(\)@=\{\}]*(?:$|\s)"
    env_vars = re.findall(regex, mars_docker_env_secrets)
    # cleanup the env var
    env_vars_clean = []
    for env_var in env_vars:
        env_var = env_var.strip()
        par, val = env_var.split("=", 1)
        par = par.strip()
        val = val.strip()
        if val[0] == "'" and val[-1] == "'" and len(val) > 1:
            # remove single quotes from the beginning and end of the value
            val = val[1:-1]
        # Revert if any single quotes are already escaped
        val =  val.replace(r"'\''", r"'")
        # Escape any single quotes in the value
        val =  val.replace(r"'", r"'\''")
        env_vars_clean.append("{}='{}'".format(par, val))
    return env_vars_clean

if __name__ == "__main__":
    mars_docker_env_secrets = os.getenv("MARS_DOCKER_ENV_SECRETS")
    parsed_mars_docker_env_secrets = parse_escape_docker_env_secrets(mars_docker_env_secrets)
    for env_var in parsed_mars_docker_env_secrets:
        print('export {env_var}'.format(env_var=env_var))