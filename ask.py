# ask.py
import sys
from agent import agent

question = " ".join(sys.argv[1:]) or "Which 5 machines had the most failures?"
result = agent.invoke(
    {"messages": [{"role": "user", "content": question}]},
    config={"recursion_limit": 25},  # hard stop on runaway loops
)
for m in result["messages"]:
    m.pretty_print()
