# agent.py
import os
from typing import Literal
from langchain.messages import ToolMessage
from guardrail import validate_sql
from dotenv import load_dotenv
from langchain.messages import AIMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from tools import tools

load_dotenv()

# CHANGE: gpt-6-luna via the Responses API.
model = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-6-luna"),
    use_responses_api=True,
    reasoning={"effort": "low"},
)

list_tables_tool = next(t for t in tools if t.name == "sql_db_list_tables")
get_schema_tool = next(t for t in tools if t.name == "sql_db_schema")
run_query_tool = next(t for t in tools if t.name == "sql_db_query")

get_schema_node = ToolNode([get_schema_tool], name="get_schema")
run_query_node = ToolNode([run_query_tool], name="run_query")


# CHANGE: the tutorial builds a fake tool call here. We simply call the
# tool in Python and hand the model the result as a message. Same effect,
# fewer moving parts.
def list_tables(state: MessagesState):
    tables = list_tables_tool.invoke({})
    return {"messages": [AIMessage(f"Available tables: {tables}")]}


def call_get_schema(state: MessagesState):
    llm_with_tools = model.bind_tools([get_schema_tool], tool_choice="any")
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


# CHANGE: dialect is postgresql, and a few domain hints are added.
generate_query_system_prompt = """
You are an agent designed to interact with a PostgreSQL database about
industrial machines: their telemetry, errors, maintenance and failures in 2015.
Given an input question, create a syntactically correct PostgreSQL query to run,
then look at the results of the query and return the answer. Unless the user
specifies a specific number of examples they wish to obtain, always limit your
query to at most 10 results.

You can order the results by a relevant column to return the most interesting
examples in the database. Never query for all the columns from a specific table,
only ask for the relevant columns given the question.

The telemetry table is large (hourly rows). Always aggregate it (AVG, MAX, COUNT)
or filter it by machine_id and a date range; never select raw telemetry rows
without a LIMIT.

DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.) to the database.
In your final answer, state the result plainly and include the SQL you ran.
"""


def generate_query(state: MessagesState):
    system_message = {"role": "system", "content": generate_query_system_prompt}
    llm_with_tools = model.bind_tools([run_query_tool])
    response = llm_with_tools.invoke([system_message] + state["messages"])
    return {"messages": [response]}


check_query_system_prompt = """
You are a SQL expert with a strong attention to detail.
Double check the PostgreSQL query for common mistakes, including:
- Using NOT IN with NULL values
- Using UNION when UNION ALL should have been used
- Using BETWEEN for exclusive ranges
- Data type mismatch in predicates
- Properly quoting identifiers
- Using the correct number of arguments for functions
- Casting to the correct data type
- Using the proper columns for joins

If there are any of the above mistakes, rewrite the query. If there are no mistakes,
just reproduce the original query.

You will call the appropriate tool to execute the query after running this check.
"""


def check_query(state: MessagesState):
    system_message = {"role": "system", "content": check_query_system_prompt}
    tool_call = state["messages"][-1].tool_calls[0]
    user_message = {"role": "user", "content": tool_call["args"]["query"]}
    llm_with_tools = model.bind_tools([run_query_tool], tool_choice="any")
    response = llm_with_tools.invoke([system_message, user_message])
    response.id = state["messages"][-1].id  # replaces the unchecked query
    return {"messages": [response]}


def validate_query(state: MessagesState):
    last = state["messages"][-1]
    blocked = []
    for tc in last.tool_calls:
        ok, reason = validate_sql(tc["args"].get("query", ""))
        if not ok:
            blocked.append(reason)
    if not blocked:
        return {}  # nothing to add; go on to run_query
    msg = (
        f"Query blocked by guardrail: {'; '.join(blocked)}. "
        "Write a single read-only SELECT statement."
    )
    return {
        "messages": [
            ToolMessage(content=msg, tool_call_id=tc["id"]) for tc in last.tool_calls
        ]
    }


def after_validation(state: MessagesState) -> Literal["run_query", "generate_query"]:
    if isinstance(state["messages"][-1], ToolMessage):
        return "generate_query"  # blocked: let the model rethink
    return "run_query"


def should_continue(state: MessagesState) -> Literal["__end__", "check_query"]:
    last_message = state["messages"][-1]
    if not last_message.tool_calls:
        return END
    return "check_query"


builder = StateGraph(MessagesState)
builder.add_node(list_tables)
builder.add_node(call_get_schema)
builder.add_node(get_schema_node, "get_schema")
builder.add_node(generate_query)
builder.add_node(check_query)
builder.add_node(run_query_node, "run_query")

builder.add_edge(START, "list_tables")
builder.add_edge("list_tables", "call_get_schema")
builder.add_edge("call_get_schema", "get_schema")
builder.add_edge("get_schema", "generate_query")
builder.add_conditional_edges("generate_query", should_continue)
builder.add_node(validate_query)
builder.add_edge("check_query", "validate_query")
builder.add_conditional_edges("validate_query", after_validation)
builder.add_edge("run_query", "generate_query")

agent = builder.compile()
