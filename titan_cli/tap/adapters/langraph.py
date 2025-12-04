"""
LangGraph adapter for TitanTools.

This module provides adapters to convert TitanTools into LangGraph-compatible tools.
Implements the ToolAdapter protocol.
"""

from __future__ import annotations

from typing import Any, Optional

try:
    from langchain_core.tools import tool as langchain_tool
    try:
        # Try new import location first (LangGraph v1.0+)
        from langchain.agents import create_react_agent
    except ImportError:
        # Fall back to deprecated location
        from langgraph.prebuilt import create_react_agent
    LANGRAPH_AVAILABLE = True
except ImportError:
    LANGRAPH_AVAILABLE = False


class LangGraphAdapter:
    """
    Adapter for LangGraph/LangChain.
    
    Implements the ToolAdapter protocol to convert TitanTools into
    LangGraph-compatible tools.
    """
    
    @staticmethod
    def convert_tool(titan_tool: TitanTool) -> Any:
        """
        Convert a TitanTool to a LangGraph/LangChain tool.
        
        Args:
            titan_tool: The TitanTool to convert
        
        Returns:
            A LangChain tool object
        
        Raises:
            ImportError: If LangGraph is not installed
        """
        if not LANGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is not installed. Install it with: pip install titanagents[langraph]"
            )
        
        # Create a wrapper function with the tool's description as docstring
        def tool_wrapper(**kwargs: Any) -> Any:
            """Tool wrapper for LangChain."""
            return titan_tool.execute(**kwargs)
        
        # Set the docstring to match the TitanTool description
        tool_wrapper.__doc__ = titan_tool.description
        tool_wrapper.__name__ = titan_tool.name
        
        # Create a LangChain tool using the decorator
        langchain_tool_instance = langchain_tool(tool_wrapper)
        
        return langchain_tool_instance
    
    @staticmethod
    def convert_tools(titan_tools: list[TitanTool]) -> list[Any]:
        """
        Convert a list of TitanTools to LangGraph tools.
        
        Args:
            titan_tools: List of TitanTools to convert
        
        Returns:
            List of LangChain tool objects
        """
        return [LangGraphAdapter.convert_tool(tool) for tool in titan_tools]
    
    @staticmethod
    def execute_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        tools: list[TitanTool],
    ) -> Any:
        """
        Execute a tool from LangGraph's response.
        
        Note: LangGraph typically handles execution internally,
        but this method is provided for protocol compliance.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            tools: List of available TitanTools
        
        Returns:
            The result of the tool execution
        
        Raises:
            ValueError: If the tool is not found
        """
        tool = next((t for t in tools if t.name == tool_name), None)
        
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        return tool.execute(**tool_input)
    
    @staticmethod
    def create_agent(
        tools: list[TitanTool],
        model: Any,
        system_prompt: Optional[str] = None,
    ) -> Any:
        """
        Create a LangGraph ReAct agent with the given tools.
        
        Args:
            tools: List of TitanTools to make available to the agent
            model: The LLM model to use (e.g., ChatAnthropic, ChatOpenAI)
            system_prompt: Optional system prompt for the agent
        
        Returns:
            A configured LangGraph agent
        
        Example:
            from langchain_anthropic import ChatAnthropic
            from titan_cli.core import PluginManager
            from titan_cli.tap.langraph import LangGraphAdapter
            
            pm = PluginManager()
            pm.discover_plugins("./plugins")
            
            model = ChatAnthropic(model="claude-3-5-sonnet-20241022")
            agent = LangGraphAdapter.create_agent(
                tools=pm.get_all_tools(),
                model=model,
                system_prompt="You are a helpful file system assistant."
            )
            
            result = agent.invoke({"messages": [("user", "Read /tmp/test.txt")]})
        """
        if not LANGRAPH_AVAILABLE:
            raise ImportError(
                "LangGraph is not installed. Install it with: pip install titanagents[langraph]"
            )
        
        # Convert TitanTools to LangGraph tools
        langraph_tools = LangGraphAdapter.convert_tools(tools)
        
        # Create the agent
        agent = create_react_agent(
            model=model,
            tools=langraph_tools,
            state_modifier=system_prompt,
        )
        
        return agent


# Backward compatibility aliases
def to_langraph_tool(titan_tool: TitanTool) -> Any:
    """Legacy function - use LangGraphAdapter.convert_tool() instead."""
    return LangGraphAdapter.convert_tool(titan_tool)


def to_langraph_tools(titan_tools: list[TitanTool]) -> list[Any]:
    """Legacy function - use LangGraphAdapter.convert_tools() instead."""
    return LangGraphAdapter.convert_tools(titan_tools)


def create_agent(
    tools: list[TitanTool],
    model: Any,
    system_prompt: Optional[str] = None,
) -> Any:
    """Legacy function - use LangGraphAdapter.create_agent() instead."""
    return LangGraphAdapter.create_agent(tools, model, system_prompt)
