from typing import Any, Dict
from agno.tools import Toolkit
from src.workflows.text2sql_workflow import Text2SQLWorkflow
from config import get_config

class Text2SQLWorkflowTool(Toolkit):
    
    def __init__(self):
        super().__init__(name="text2sql_workflow_tool")
        self.register(self.answer_data_question)
        # Load config to get database name
        self.config = get_config()

    def answer_data_question(self, question: str) -> str:
        """
        Retrieves data by generating and executing SQL queries against the database.
        Use this tool when the user asks a question that requires data analysis or retrieval.
        
        Args:
            question (str): The user's natural language question.
            
        Returns:
            str: The results of the query execution.
        """
        # Get database name from config (uses ATHENA_DATABASE env var or default)
        database_name = self.config.mcp.athena_database
        
        # Create and run the workflow with proper database name
        workflow = Text2SQLWorkflow(
            user_query=question,
            database_name=database_name,
            region_name=self.config.aws.region
        )
        workflow.run_complete_workflow()
        
        # Return the result from the workflow state
        if workflow.query_result:
            return workflow.query_result
        return "No results found or error occurred."
