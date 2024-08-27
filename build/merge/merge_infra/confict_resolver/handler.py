
import os


def handleImportConflict(local, remote, input, conflictStart, conflictEnd, localDiff, remoteDiff, localRemoteCommon):
    localAndRemote = local + remote
    importList = []
    for line in localAndRemote:
        if line not in importList:
            importList.append(line)
    while len(importList) < conflictEnd - conflictStart + 1:
        importList.append("\n")
    return importList


def handleCommentConflict(local, remote, input, conflictStart, conflictEnd, localDiff, remoteDiff, localRemoteCommon):
    localAndRemote = local + remote
    commentList = []
    for line in localAndRemote:
        if line not in commentList:
            commentList.append(line)
    while len(commentList) < conflictEnd - conflictStart + 1:
        commentList.append("\n")
    return commentList


def handleListAppendConflict(local, remote, input, conflictStart, conflictEnd, localDiff, remoteDiff, localRemoteCommon):
    # Prioritizes remote changes over local changes
    localAndRemote = remote + local
    lst = []
    listNames = set()
    for line in localAndRemote:
        if (".append" not in line) and ("+= [" not in line) and line not in lst:
            lst.append(line)
        elif (".append" in line) and (line[0:line.index(".append")] not in listNames) and line not in lst:
            lst.append(line)
            listNames.add(line[0:line.index(".append")])
        elif ("+= [" in line) and (line[0:line.index("+") - 1] not in listNames) and line not in lst:
            lst.append(line)
            listNames.add(line[0:line.index("+") - 1])
    while len(lst) < conflictEnd - conflictStart + 1:
        lst.append("\n")
    return lst


def handleWhitespaceConflict(local, remote, input, conflictStart, conflictEnd, localDiff, remoteDiff, localRemoteCommon):
    formattedOutputRemote = []
    for line in remote:
        stripped_line = line.strip()
        idx = line.index(stripped_line)
        formattedOutputRemote.append(
            line[0:idx])
    return formattedOutputRemote


def handleElseConflict(input):
    raise NotImplemented
