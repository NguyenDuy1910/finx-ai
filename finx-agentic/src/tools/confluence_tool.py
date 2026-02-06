"""
Confluence Knowledge Base Tools with Vector Database Storage

This module provides tools to load, process, and store Confluence documentation
in a vector database for semantic search and retrieval.

Features:
- Load Confluence pages and spaces
- Chunk content for optimal embedding
- Generate embeddings and store in Qdrant
- Semantic search over knowledge base
- Update and sync documentation
"""

import json
import logging
from typing import Any, Dict, List, Optional, Union
from os import getenv
import hashlib
import re
from datetime import datetime

from agno.tools import Toolkit
from agno.utils.log import log_info, logger

try:
    from atlassian import Confluence
except (ModuleNotFoundError, ImportError):
    raise ImportError("atlassian-python-api not installed. Please install using `pip install atlassian-python-api`")

try:
    import requests
except (ModuleNotFoundError, ImportError):
    raise ImportError("requests not installed. Please install using `pip install requests`")

# Import local storage modules
from src.storage.embedding_service import get_embedding_service, EmbeddingService
from src.storage.qdrant_client import get_qdrant_client, QdrantClientWrapper

logger = logging.getLogger(__name__)


class ConfluenceLoaderTools(Toolkit):
    """
    Confluence knowledge base tools with vector database integration.
    
    This toolkit provides methods to:
    1. Load content from Confluence (pages, spaces)
    2. Process and chunk content for embedding
    3. Generate embeddings using sentence-transformers
    4. Store embeddings in Qdrant vector database
    5. Search knowledge base semantically
    6. Manage and sync documentation
    """
    
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_ssl: bool = True,
        collection_name: str = "confluence_knowledge",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2",
        **kwargs,
    ):
        """
        Initialize Confluence Loader Tools with vector database.
        
        Args:
            username: Confluence username (or use CONFLUENCE_USERNAME env var)
            password: Confluence password (or use CONFLUENCE_PASSWORD env var)
            url: Confluence instance URL (or use CONFLUENCE_URL env var)
            api_key: Confluence API key (or use CONFLUENCE_API_KEY env var)
            verify_ssl: Whether to verify SSL certificates
            collection_name: Name of Qdrant collection for storage
            chunk_size: Size of text chunks for embedding
            chunk_overlap: Overlap between chunks
            embedding_model: Model for generating embeddings
        """
        # Initialize Confluence connection
        self.url = url or getenv("CONFLUENCE_URL")
        self.username = username or getenv("CONFLUENCE_USERNAME")
        self.password = api_key or getenv("CONFLUENCE_API_KEY") or password or getenv("CONFLUENCE_PASSWORD")
        
        if not self.url:
            raise ValueError(
                "Confluence URL not provided. Pass it in the constructor or set CONFLUENCE_URL environment variable"
            )
        
        if not self.username:
            raise ValueError(
                "Confluence username not provided. Pass it in the constructor or set CONFLUENCE_USERNAME environment variable"
            )
        
        if not self.password:
            raise ValueError("Confluence API KEY or password not provided")
        
        # Setup Confluence client
        session = requests.Session()
        session.verify = verify_ssl
        
        if not verify_ssl:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        self.confluence = Confluence(
            url=self.url,
            username=self.username,
            password=self.password,
            verify_ssl=verify_ssl,
            session=session,
        )
        
        # Initialize vector database components
        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Get embedding service and Qdrant client
        self.embedding_service: EmbeddingService = get_embedding_service(embedding_model)
        self.qdrant_client: QdrantClientWrapper = get_qdrant_client()
        
        # Ensure collection exists
        vector_size = self.embedding_service.get_dimension()
        self.qdrant_client.create_collection(
            collection_name=self.collection_name,
            vector_size=vector_size,
            distance="Cosine"
        )
        
        logger.info(f"Initialized ConfluenceLoaderTools with collection '{self.collection_name}'")
        
        # Register tools
        tools: List[Any] = [
            self.load_page_to_knowledge_base,
            self.load_space_to_knowledge_base,
            self.search_knowledge_base,
            self.get_page_content,
            self.get_space_info,
            self.list_all_spaces,
            self.list_pages_in_space,
            self.sync_page,
            self.get_knowledge_base_stats,
        ]
        
        super().__init__(name="confluence_knowledge_tools", tools=tools, **kwargs)
    
    def _clean_html(self, html_content: str) -> str:
        """
        Clean HTML content and extract text.
        
        Args:
            html_content: Raw HTML content
            
        Returns:
            Cleaned text content
        """
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_content)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        # Remove special characters
        text = text.strip()
        return text
    
    def _chunk_text(self, text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split text into chunks with overlap.
        
        Args:
            text: Text to chunk
            metadata: Base metadata for chunks
            
        Returns:
            List of chunk dictionaries
        """
        chunks = []
        words = text.split()
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            if len(chunk_text.strip()) > 50:  # Minimum chunk size
                chunk_metadata = metadata.copy()
                chunk_metadata.update({
                    "chunk_index": len(chunks),
                    "chunk_text": chunk_text,
                    "word_count": len(chunk_words)
                })
                chunks.append(chunk_metadata)
        
        logger.info(f"Created {len(chunks)} chunks from text of {len(words)} words")
        return chunks
    
    def _generate_doc_id(self, space_key: str, page_id: str, chunk_index: int = 0) -> str:
        """
        Generate unique document ID.
        
        Args:
            space_key: Confluence space key
            page_id: Confluence page ID
            chunk_index: Index of chunk
            
        Returns:
            Unique document ID
        """
        id_string = f"{space_key}:{page_id}:{chunk_index}"
        return hashlib.md5(id_string.encode()).hexdigest()
    
    def load_page_to_knowledge_base(
        self,
        space_name: str,
        page_title: str,
        update_if_exists: bool = True
    ) -> str:
        """
        Load a Confluence page into the knowledge base.
        
        This method:
        1. Retrieves the page content from Confluence
        2. Cleans and chunks the content
        3. Generates embeddings for each chunk
        4. Stores chunks with embeddings in Qdrant
        
        Args:
            space_name: Name of the Confluence space
            page_title: Title of the page to load
            update_if_exists: Whether to update if page already exists
            
        Returns:
            JSON string with status and details
        """
        try:
            log_info(f"Loading page '{page_title}' from space '{space_name}'")
            
            # Get space key
            space_key = self._get_space_key(space_name)
            if not space_key:
                return json.dumps({"error": f"Space '{space_name}' not found"})
            
            # Get page content
            page = self.confluence.get_page_by_title(space=space_key, title=page_title, expand="body.storage,version")
            
            if not page:
                return json.dumps({"error": f"Page '{page_title}' not found in space '{space_name}'"})
            
            page_id = page['id']
            content = page.get('body', {}).get('storage', {}).get('value', '')
            version = page.get('version', {}).get('number', 1)
            
            # Clean content
            text_content = self._clean_html(content)
            
            if len(text_content.strip()) < 50:
                return json.dumps({"error": "Page content too short or empty"})
            
            # Prepare metadata
            base_metadata = {
                "source": "confluence",
                "space_key": space_key,
                "space_name": space_name,
                "page_id": page_id,
                "page_title": page_title,
                "page_url": f"{self.url}/spaces/{space_key}/pages/{page_id}",
                "version": version,
                "loaded_at": datetime.utcnow().isoformat(),
            }
            
            # Chunk content
            chunks = self._chunk_text(text_content, base_metadata)
            
            # Generate embeddings
            chunk_texts = [chunk["chunk_text"] for chunk in chunks]
            embeddings = self.embedding_service.embed(chunk_texts)
            
            # Prepare for storage
            doc_ids = [
                self._generate_doc_id(space_key, page_id, i)
                for i in range(len(chunks))
            ]
            
            # Store in Qdrant
            success = self.qdrant_client.insert_vectors(
                collection_name=self.collection_name,
                vectors=embeddings,
                payloads=chunks,
                ids=doc_ids
            )
            
            if success:
                result = {
                    "status": "success",
                    "page_title": page_title,
                    "space_name": space_name,
                    "page_id": page_id,
                    "chunks_stored": len(chunks),
                    "collection": self.collection_name
                }
                logger.info(f"Successfully loaded page '{page_title}' with {len(chunks)} chunks")
                return json.dumps(result)
            else:
                return json.dumps({"error": "Failed to store vectors in database"})
                
        except Exception as e:
            logger.error(f"Error loading page to knowledge base: {e}")
            return json.dumps({"error": str(e)})
    
    def load_space_to_knowledge_base(
        self,
        space_name: str,
        max_pages: Optional[int] = None,
        update_if_exists: bool = True
    ) -> str:
        """
        Load all pages from a Confluence space into the knowledge base.
        
        Args:
            space_name: Name of the Confluence space
            max_pages: Maximum number of pages to load (None for all)
            update_if_exists: Whether to update existing pages
            
        Returns:
            JSON string with status and details
        """
        try:
            log_info(f"Loading space '{space_name}' to knowledge base")
            
            # Get space key
            space_key = self._get_space_key(space_name)
            if not space_key:
                return json.dumps({"error": f"Space '{space_name}' not found"})
            
            # Get all pages in space
            pages = self.confluence.get_all_pages_from_space(
                space=space_key,
                start=0,
                limit=max_pages or 1000,
                expand="body.storage,version"
            )
            
            if not pages:
                return json.dumps({"error": f"No pages found in space '{space_name}'"})
            
            # Limit pages if specified
            if max_pages:
                pages = pages[:max_pages]
            
            loaded_pages = []
            failed_pages = []
            total_chunks = 0
            
            for page in pages:
                try:
                    page_title = page.get('title', '')
                    result = self.load_page_to_knowledge_base(
                        space_name=space_name,
                        page_title=page_title,
                        update_if_exists=update_if_exists
                    )
                    
                    result_dict = json.loads(result)
                    if result_dict.get("status") == "success":
                        loaded_pages.append(page_title)
                        total_chunks += result_dict.get("chunks_stored", 0)
                    else:
                        failed_pages.append({
                            "title": page_title,
                            "error": result_dict.get("error", "Unknown error")
                        })
                        
                except Exception as e:
                    failed_pages.append({
                        "title": page.get('title', 'Unknown'),
                        "error": str(e)
                    })
            
            result = {
                "status": "completed",
                "space_name": space_name,
                "total_pages": len(pages),
                "loaded_pages": len(loaded_pages),
                "failed_pages": len(failed_pages),
                "total_chunks": total_chunks,
                "collection": self.collection_name,
                "failures": failed_pages if failed_pages else None
            }
            
            logger.info(f"Loaded {len(loaded_pages)}/{len(pages)} pages from space '{space_name}'")
            return json.dumps(result)
            
        except Exception as e:
            logger.error(f"Error loading space to knowledge base: {e}")
            return json.dumps({"error": str(e)})
    
    def search_knowledge_base(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.7,
        space_filter: Optional[str] = None
    ) -> str:
        """
        Search the knowledge base using semantic similarity.
        
        Args:
            query: Search query
            limit: Maximum number of results
            score_threshold: Minimum similarity score (0-1)
            space_filter: Optional space name to filter results
            
        Returns:
            JSON string with search results
        """
        try:
            log_info(f"Searching knowledge base for: '{query}'")
            
            # Generate query embedding
            query_embedding = self.embedding_service.embed(query)
            
            # Build filters
            filters = None
            if space_filter:
                space_key = self._get_space_key(space_filter)
                if space_key:
                    filters = {"space_key": space_key}
            
            # Search in Qdrant
            results = self.qdrant_client.search_vectors(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                filter_conditions=filters
            )
            
            # Format results
            formatted_results = []
            for result in results:
                payload = result.get("payload", {})
                formatted_results.append({
                    "score": result.get("score"),
                    "page_title": payload.get("page_title"),
                    "space_name": payload.get("space_name"),
                    "page_url": payload.get("page_url"),
                    "content": payload.get("chunk_text", "")[:500],  # First 500 chars
                    "chunk_index": payload.get("chunk_index"),
                    "version": payload.get("version"),
                })
            
            response = {
                "status": "success",
                "query": query,
                "results_count": len(formatted_results),
                "results": formatted_results
            }
            
            logger.info(f"Found {len(formatted_results)} results for query")
            return json.dumps(response, indent=2)
            
        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return json.dumps({"error": str(e)})
    
    def get_page_content(self, space_name: str, page_title: str) -> str:
        """
        Get the raw content of a Confluence page.
        
        Args:
            space_name: Name of the Confluence space
            page_title: Title of the page
            
        Returns:
            JSON string with page content
        """
        try:
            space_key = self._get_space_key(space_name)
            if not space_key:
                return json.dumps({"error": f"Space '{space_name}' not found"})
            
            page = self.confluence.get_page_by_title(
                space=space_key,
                title=page_title,
                expand="body.storage,version"
            )
            
            if not page:
                return json.dumps({"error": f"Page '{page_title}' not found"})
            
            content = page.get('body', {}).get('storage', {}).get('value', '')
            text_content = self._clean_html(content)
            
            result = {
                "page_title": page_title,
                "page_id": page['id'],
                "space_name": space_name,
                "version": page.get('version', {}).get('number'),
                "content": text_content,
                "url": f"{self.url}/spaces/{space_key}/pages/{page['id']}"
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting page content: {e}")
            return json.dumps({"error": str(e)})
    
    def get_space_info(self, space_name: str) -> str:
        """
        Get information about a Confluence space.
        
        Args:
            space_name: Name of the space
            
        Returns:
            JSON string with space information
        """
        try:
            space_key = self._get_space_key(space_name)
            if not space_key:
                return json.dumps({"error": f"Space '{space_name}' not found"})
            
            space = self.confluence.get_space(space_key, expand="description.plain,homepage")
            
            result = {
                "name": space.get('name'),
                "key": space.get('key'),
                "type": space.get('type'),
                "description": space.get('description', {}).get('plain', {}).get('value', ''),
                "url": f"{self.url}/spaces/{space_key}"
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting space info: {e}")
            return json.dumps({"error": str(e)})
    
    def list_all_spaces(self) -> str:
        """
        List all available Confluence spaces.
        
        Returns:
            JSON string with list of spaces
        """
        try:
            spaces = self.confluence.get_all_spaces(start=0, limit=100)
            
            space_list = [
                {
                    "name": space.get('name'),
                    "key": space.get('key'),
                    "type": space.get('type')
                }
                for space in spaces.get('results', [])
            ]
            
            result = {
                "status": "success",
                "count": len(space_list),
                "spaces": space_list
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error listing spaces: {e}")
            return json.dumps({"error": str(e)})
    
    def list_pages_in_space(self, space_name: str, limit: int = 50) -> str:
        """
        List all pages in a Confluence space.
        
        Args:
            space_name: Name of the space
            limit: Maximum number of pages to return
            
        Returns:
            JSON string with list of pages
        """
        try:
            space_key = self._get_space_key(space_name)
            if not space_key:
                return json.dumps({"error": f"Space '{space_name}' not found"})
            
            pages = self.confluence.get_all_pages_from_space(
                space=space_key,
                start=0,
                limit=limit
            )
            
            page_list = [
                {
                    "title": page.get('title'),
                    "id": page.get('id'),
                    "type": page.get('type')
                }
                for page in pages
            ]
            
            result = {
                "status": "success",
                "space_name": space_name,
                "count": len(page_list),
                "pages": page_list
            }
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error listing pages: {e}")
            return json.dumps({"error": str(e)})
    
    def sync_page(self, space_name: str, page_title: str) -> str:
        """
        Sync a page by reloading it if it has been updated in Confluence.
        
        Args:
            space_name: Name of the space
            page_title: Title of the page to sync
            
        Returns:
            JSON string with sync status
        """
        try:
            # Just reload the page with update enabled
            result = self.load_page_to_knowledge_base(
                space_name=space_name,
                page_title=page_title,
                update_if_exists=True
            )
            
            result_dict = json.loads(result)
            if result_dict.get("status") == "success":
                result_dict["action"] = "synced"
            
            return json.dumps(result_dict, indent=2)
            
        except Exception as e:
            logger.error(f"Error syncing page: {e}")
            return json.dumps({"error": str(e)})
    
    def get_knowledge_base_stats(self) -> str:
        """
        Get statistics about the knowledge base collection.
        
        Returns:
            JSON string with collection statistics
        """
        try:
            info = self.qdrant_client.get_collection_info(self.collection_name)
            
            if info:
                result = {
                    "status": "success",
                    "collection_name": self.collection_name,
                    "total_chunks": info.get("points_count", 0),
                    "collection_status": info.get("status"),
                    "embedding_model": self.embedding_service.model_name,
                    "vector_dimension": self.embedding_service.get_dimension(),
                    "cache_size": self.embedding_service.get_cache_size()
                }
            else:
                result = {"error": "Collection not found"}
            
            return json.dumps(result, indent=2)
            
        except Exception as e:
            logger.error(f"Error getting knowledge base stats: {e}")
            return json.dumps({"error": str(e)})
    
    def _get_space_key(self, space_name: str) -> Optional[str]:
        """
        Get space key from space name.
        
        Args:
            space_name: Name of the space
            
        Returns:
            Space key or None if not found
        """
        try:
            spaces = self.confluence.get_all_spaces(start=0, limit=500)
            
            for space in spaces.get('results', []):
                if space.get('name', '').lower() == space_name.lower():
                    return space.get('key')
            
            # If exact match not found, try searching
            # Check if the input might already be a key
            try:
                space = self.confluence.get_space(space_name)
                if space:
                    return space.get('key')
            except:
                pass
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting space key: {e}")
            return None
