class UsageError(Exception):
    """The command line itself is wrong (unknown command, missing argument).

    Distinct from the domain errors of services/, which mean valid input met
    a rule of the data; the CLI reports the two with different exit codes.
    """

