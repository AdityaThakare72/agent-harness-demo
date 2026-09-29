from harness.model import reply

FILES = ["standup_notes.txt", "bug_report.txt", "reading_list.txt"]

REPORT = """# Sandbox summary

- standup_notes.txt: login redesign done, payments API blocked on expired keys, deploy freeze Friday 17:00.
- bug_report.txt: CSV export drops the last row (suspected off-by-one in export.py).
- reading_list.txt: three items on data systems, pragmatic programming and RAG evaluation.
"""

DONE = "Finished. (This reply came from the scripted FakeModel, not a real model.)"


def v0():
    return [reply("I can't open files on your machine, so I can't read sandbox/. Paste the contents and I'll summarize them.")]


def v1():
    reads = [reply("", ("read_file", {"path": f"sandbox/{f}"})) for f in FILES]
    return reads + [reply("Summary: login redesign is done, payments is blocked on expired keys, "
                          "a CSV export bug drops the last row, and the reading list covers data systems and RAG.")]


def v2():
    reads = [reply("", ("read_file", {"path": f"sandbox/{f}"})) for f in FILES]
    return [reply("", ("list_dir", {"path": "sandbox"}))] + reads + [
        reply("", ("write_file", {"path": "sandbox/report.md", "content": REPORT})), reply(DONE)]


def v3():
    reads = [reply("", ("read_file", {"path": f})) for f in FILES]
    return [reply("", ("list_dir", {"path": "."}))] + reads + [
        reply("", ("write_file", {"path": "report.md", "content": REPORT})), reply(DONE)]


def v4():
    def plan(*statuses):
        steps = ["List the folder", "Read every file", "Write report.md"]
        return reply("", ("update_todos", {"todos": [{"text": t, "status": s} for t, s in zip(steps, statuses)]}))

    reads = [reply("", ("read_file", {"path": f})) for f in FILES]
    return [plan("in_progress", "pending", "pending"), reply("", ("list_dir", {"path": "."})),
            plan("done", "in_progress", "pending")] + reads + [
        plan("done", "done", "in_progress"), reply("", ("write_file", {"path": "report.md", "content": REPORT})),
        plan("done", "done", "done"), reply(DONE)]
