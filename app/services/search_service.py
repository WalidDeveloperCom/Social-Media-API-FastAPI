"""
Search Service for Elasticsearch integration
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import ElasticsearchException

from app.config import settings
from app.models.post import Post
from app.models.user import User
from app.models.comment import Comment

logger = logging.getLogger(__name__)


class SearchService:
    def __init__(self):
        self.es_client = None
        self._initialize_client()

    def _initialize_client(self):
        """Initialize Elasticsearch client"""
        try:
            if not settings.ELASTICSEARCH_URL:
                logger.warning("Elasticsearch URL not configured. Search service will be disabled.")
                return

            self.es_client = AsyncElasticsearch(
                hosts=[settings.ELASTICSEARCH_URL],
                # Add authentication if needed
                # basic_auth=('username', 'password'),
                # Or API key
                # api_key=('api_key_id', 'api_key_secret'),
                verify_certs=False,  # Set to True in production with proper certs
                request_timeout=30
            )
            logger.info("Elasticsearch client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch client: {e}")
            self.es_client = None

    async def is_available(self) -> bool:
        """Check if Elasticsearch is available"""
        if not self.es_client:
            return False
        
        try:
            await self.es_client.ping()
            return True
        except Exception as e:
            logger.error(f"Elasticsearch ping failed: {e}")
            return False

    async def create_indices(self):
        """Create Elasticsearch indices if they don't exist"""
        if not await self.is_available():
            logger.warning("Elasticsearch not available, skipping index creation")
            return

        try:
            # Posts index
            posts_index_body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {
                        "analyzer": {
                            "default": {
                                "type": "standard"
                            },
                            "text_analyzer": {
                                "type": "custom",
                                "tokenizer": "standard",
                                "filter": ["lowercase", "stop", "snowball"]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "integer"},
                        "user_id": {"type": "integer"},
                        "content": {
                            "type": "text",
                            "analyzer": "text_analyzer",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "media_url": {"type": "keyword"},
                        "media_type": {"type": "keyword"},
                        "is_public": {"type": "boolean"},
                        "location": {"type": "keyword"},
                        "like_count": {"type": "integer"},
                        "comment_count": {"type": "integer"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "user": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "username": {"type": "keyword"},
                                "full_name": {"type": "text"},
                                "profile_picture": {"type": "keyword"}
                            }
                        }
                    }
                }
            }

            # Users index
            users_index_body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {
                        "analyzer": {
                            "default": {
                                "type": "standard"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "integer"},
                        "username": {
                            "type": "text",
                            "fields": {
                                "keyword": {"type": "keyword"}
                            }
                        },
                        "email": {"type": "keyword"},
                        "full_name": {"type": "text"},
                        "bio": {"type": "text"},
                        "profile_picture": {"type": "keyword"},
                        "is_active": {"type": "boolean"},
                        "is_verified": {"type": "boolean"},
                        "followers_count": {"type": "integer"},
                        "following_count": {"type": "integer"},
                        "posts_count": {"type": "integer"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"}
                    }
                }
            }

            # Comments index
            comments_index_body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "analysis": {
                        "analyzer": {
                            "default": {
                                "type": "standard"
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "id": {"type": "integer"},
                        "post_id": {"type": "integer"},
                        "user_id": {"type": "integer"},
                        "content": {"type": "text"},
                        "parent_id": {"type": "integer"},
                        "like_count": {"type": "integer"},
                        "created_at": {"type": "date"},
                        "updated_at": {"type": "date"},
                        "user": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "username": {"type": "keyword"},
                                "full_name": {"type": "text"}
                            }
                        },
                        "post": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "integer"},
                                "content": {"type": "text"}
                            }
                        }
                    }
                }
            }

            # Create indices if they don't exist
            indices = {
                "posts": posts_index_body,
                "users": users_index_body,
                "comments": comments_index_body
            }

            for index_name, index_body in indices.items():
                if not await self.es_client.indices.exists(index=index_name):
                    await self.es_client.indices.create(
                        index=index_name,
                        body=index_body
                    )
                    logger.info(f"Created Elasticsearch index: {index_name}")
                else:
                    logger.info(f"Elasticsearch index already exists: {index_name}")

        except Exception as e:
            logger.error(f"Error creating Elasticsearch indices: {e}")

    async def index_post(self, post: Post, user: Optional[User] = None):
        """Index a post in Elasticsearch"""
        if not await self.is_available():
            return

        try:
            # If user not provided, we need to get it from the post
            # This is a simplified version
            post_data = {
                "id": post.id,
                "user_id": post.user_id,
                "content": post.content,
                "media_url": post.media_url,
                "media_type": post.media_type,
                "is_public": post.is_public,
                "location": post.location,
                "like_count": post.like_count,
                "comment_count": post.comment_count,
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "updated_at": post.updated_at.isoformat() if post.updated_at else None
            }

            if user:
                post_data["user"] = {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "profile_picture": user.profile_picture
                }

            await self.es_client.index(
                index="posts",
                id=post.id,
                body=post_data,
                refresh=True  # Make document immediately searchable
            )
            
            logger.debug(f"Indexed post {post.id} in Elasticsearch")
        except Exception as e:
            logger.error(f"Error indexing post {post.id}: {e}")

    async def update_post(self, post: Post, user: Optional[User] = None):
        """Update a post in Elasticsearch"""
        if not await self.is_available():
            return

        try:
            # First check if the post exists in the index
            exists = await self.es_client.exists(index="posts", id=post.id)
            
            if exists:
                # Update existing document
                post_data = {
                    "doc": {
                        "content": post.content,
                        "media_url": post.media_url,
                        "media_type": post.media_type,
                        "is_public": post.is_public,
                        "location": post.location,
                        "like_count": post.like_count,
                        "comment_count": post.comment_count,
                        "updated_at": post.updated_at.isoformat() if post.updated_at else None
                    }
                }

                if user:
                    post_data["doc"]["user"] = {
                        "id": user.id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "profile_picture": user.profile_picture
                    }

                await self.es_client.update(
                    index="posts",
                    id=post.id,
                    body=post_data,
                    refresh=True
                )
                
                logger.debug(f"Updated post {post.id} in Elasticsearch")
            else:
                # Index as new document
                await self.index_post(post, user)
                
        except Exception as e:
            logger.error(f"Error updating post {post.id} in Elasticsearch: {e}")

    async def delete_post(self, post_id: int):
        """Delete a post from Elasticsearch"""
        if not await self.is_available():
            return

        try:
            await self.es_client.delete(
                index="posts",
                id=post_id,
                refresh=True
            )
            
            logger.debug(f"Deleted post {post_id} from Elasticsearch")
        except Exception as e:
            # It's okay if the document doesn't exist
            if "not_found" not in str(e):
                logger.error(f"Error deleting post {post_id} from Elasticsearch: {e}")

    async def index_user(self, user: User):
        """Index a user in Elasticsearch"""
        if not await self.is_available():
            return

        try:
            user_data = {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "bio": user.bio,
                "profile_picture": user.profile_picture,
                "is_active": user.is_active,
                "is_verified": user.is_verified,
                "followers_count": user.followers_count,
                "following_count": user.following_count,
                "posts_count": user.posts_count,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None
            }

            await self.es_client.index(
                index="users",
                id=user.id,
                body=user_data,
                refresh=True
            )
            
            logger.debug(f"Indexed user {user.id} in Elasticsearch")
        except Exception as e:
            logger.error(f"Error indexing user {user.id}: {e}")

    async def update_user(self, user: User):
        """Update a user in Elasticsearch"""
        if not await self.is_available():
            return

        try:
            exists = await self.es_client.exists(index="users", id=user.id)
            
            if exists:
                user_data = {
                    "doc": {
                        "username": user.username,
                        "email": user.email,
                        "full_name": user.full_name,
                        "bio": user.bio,
                        "profile_picture": user.profile_picture,
                        "is_active": user.is_active,
                        "is_verified": user.is_verified,
                        "followers_count": user.followers_count,
                        "following_count": user.following_count,
                        "posts_count": user.posts_count,
                        "updated_at": user.updated_at.isoformat() if user.updated_at else None
                    }
                }

                await self.es_client.update(
                    index="users",
                    id=user.id,
                    body=user_data,
                    refresh=True
                )
                
                logger.debug(f"Updated user {user.id} in Elasticsearch")
            else:
                await self.index_user(user)
                
        except Exception as e:
            logger.error(f"Error updating user {user.id} in Elasticsearch: {e}")

    async def delete_user(self, user_id: int):
        """Delete a user from Elasticsearch"""
        if not await self.is_available():
            return

        try:
            await self.es_client.delete(
                index="users",
                id=user_id,
                refresh=True
            )
            
            logger.debug(f"Deleted user {user_id} from Elasticsearch")
        except Exception as e:
            if "not_found" not in str(e):
                logger.error(f"Error deleting user {user_id} from Elasticsearch: {e}")

    async def index_comment(self, comment: Comment, user: Optional[User] = None, post: Optional[Post] = None):
        """Index a comment in Elasticsearch"""
        if not await self.is_available():
            return

        try:
            comment_data = {
                "id": comment.id,
                "post_id": comment.post_id,
                "user_id": comment.user_id,
                "content": comment.content,
                "parent_id": comment.parent_id,
                "like_count": comment.like_count,
                "created_at": comment.created_at.isoformat() if comment.created_at else None,
                "updated_at": comment.updated_at.isoformat() if comment.updated_at else None
            }

            if user:
                comment_data["user"] = {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name
                }

            if post:
                comment_data["post"] = {
                    "id": post.id,
                    "content": post.content[:200] if post.content else None  # Preview
                }

            await self.es_client.index(
                index="comments",
                id=comment.id,
                body=comment_data,
                refresh=True
            )
            
            logger.debug(f"Indexed comment {comment.id} in Elasticsearch")
        except Exception as e:
            logger.error(f"Error indexing comment {comment.id}: {e}")

    async def search_posts(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
        user_id: Optional[int] = None,
        is_public: Optional[bool] = True
    ) -> List[Dict[str, Any]]:
        """Search posts using Elasticsearch"""
        if not await self.is_available():
            return []

        try:
            # Build search query
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["content", "location"],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO"
                                }
                            }
                        ],
                        "filter": []
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
                ],
                "from": skip,
                "size": limit,
                "highlight": {
                    "fields": {
                        "content": {
                            "fragment_size": 150,
                            "number_of_fragments": 1
                        }
                    }
                }
            }

            # Add filters
            if user_id is not None:
                search_body["query"]["bool"]["filter"].append(
                    {"term": {"user_id": user_id}}
                )

            if is_public is not None:
                search_body["query"]["bool"]["filter"].append(
                    {"term": {"is_public": is_public}}
                )

            response = await self.es_client.search(
                index="posts",
                body=search_body
            )

            hits = response["hits"]["hits"]
            
            results = []
            for hit in hits:
                source = hit["_source"]
                
                # Add highlighting if available
                highlighted_content = None
                if "highlight" in hit and "content" in hit["highlight"]:
                    highlighted_content = hit["highlight"]["content"][0]
                
                result = {
                    "_id": hit["_id"],
                    "_score": hit["_score"],
                    "content": source.get("content"),
                    "highlighted_content": highlighted_content,
                    "user_id": source.get("user_id"),
                    "media_url": source.get("media_url"),
                    "location": source.get("location"),
                    "like_count": source.get("like_count", 0),
                    "comment_count": source.get("comment_count", 0),
                    "created_at": source.get("created_at"),
                    "user": source.get("user")
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error searching posts: {e}")
            return []

    async def search_users(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
        only_active: bool = True
    ) -> List[Dict[str, Any]]:
        """Search users using Elasticsearch"""
        if not await self.is_available():
            return []

        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": [
                                        "username^3",  # Boost username matches
                                        "full_name^2",  # Boost full name matches
                                        "bio"
                                    ],
                                    "type": "best_fields",
                                    "fuzziness": "AUTO"
                                }
                            }
                        ],
                        "filter": []
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"followers_count": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
                ],
                "from": skip,
                "size": limit
            }

            if only_active:
                search_body["query"]["bool"]["filter"].append(
                    {"term": {"is_active": True}}
                )

            response = await self.es_client.search(
                index="users",
                body=search_body
            )

            hits = response["hits"]["hits"]
            
            results = []
            for hit in hits:
                source = hit["_source"]
                result = {
                    "_id": hit["_id"],
                    "_score": hit["_score"],
                    "username": source.get("username"),
                    "full_name": source.get("full_name"),
                    "bio": source.get("bio"),
                    "profile_picture": source.get("profile_picture"),
                    "followers_count": source.get("followers_count", 0),
                    "following_count": source.get("following_count", 0),
                    "posts_count": source.get("posts_count", 0),
                    "is_verified": source.get("is_verified", False)
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error searching users: {e}")
            return []

    async def search_comments(
        self,
        query: str,
        skip: int = 0,
        limit: int = 20,
        post_id: Optional[int] = None,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Search comments using Elasticsearch"""
        if not await self.is_available():
            return []

        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "match": {
                                    "content": {
                                        "query": query,
                                        "fuzziness": "AUTO"
                                    }
                                }
                            }
                        ],
                        "filter": []
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
                ],
                "from": skip,
                "size": limit,
                "highlight": {
                    "fields": {
                        "content": {
                            "fragment_size": 100,
                            "number_of_fragments": 1
                        }
                    }
                }
            }

            if post_id is not None:
                search_body["query"]["bool"]["filter"].append(
                    {"term": {"post_id": post_id}}
                )

            if user_id is not None:
                search_body["query"]["bool"]["filter"].append(
                    {"term": {"user_id": user_id}}
                )

            response = await self.es_client.search(
                index="comments",
                body=search_body
            )

            hits = response["hits"]["hits"]
            
            results = []
            for hit in hits:
                source = hit["_source"]
                
                highlighted_content = None
                if "highlight" in hit and "content" in hit["highlight"]:
                    highlighted_content = hit["highlight"]["content"][0]
                
                result = {
                    "_id": hit["_id"],
                    "_score": hit["_score"],
                    "content": source.get("content"),
                    "highlighted_content": highlighted_content,
                    "post_id": source.get("post_id"),
                    "user_id": source.get("user_id"),
                    "like_count": source.get("like_count", 0),
                    "created_at": source.get("created_at"),
                    "user": source.get("user"),
                    "post": source.get("post")
                }
                results.append(result)

            return results

        except Exception as e:
            logger.error(f"Error searching comments: {e}")
            return []

    async def autocomplete_users(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Autocomplete user search"""
        if not await self.is_available():
            return []

        try:
            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "multi_match": {
                                    "query": query,
                                    "fields": ["username", "full_name"],
                                    "type": "bool_prefix",
                                    "fuzziness": "AUTO"
                                }
                            }
                        ],
                        "filter": [
                            {"term": {"is_active": True}}
                        ]
                    }
                },
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"followers_count": {"order": "desc"}}
                ],
                "size": limit
            }

            response = await self.es_client.search(
                index="users",
                body=search_body
            )

            hits = response["hits"]["hits"]
            
            suggestions = []
            for hit in hits:
                source = hit["_source"]
                suggestion = {
                    "id": hit["_id"],
                    "username": source.get("username"),
                    "full_name": source.get("full_name"),
                    "profile_picture": source.get("profile_picture"),
                    "score": hit["_score"]
                }
                suggestions.append(suggestion)

            return suggestions

        except Exception as e:
            logger.error(f"Error autocomplete users: {e}")
            return []

    async def get_popular_posts(
        self,
        time_range: str = "week",  # day, week, month, year
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get popular posts based on engagement"""
        if not await self.is_available():
            return []

        try:
            # Calculate time range
            now = datetime.utcnow()
            if time_range == "day":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif time_range == "week":
                start_date = now - timedelta(days=7)
            elif time_range == "month":
                start_date = now - timedelta(days=30)
            elif time_range == "year":
                start_date = now - timedelta(days=365)
            else:
                start_date = now - timedelta(days=7)

            search_body = {
                "query": {
                    "bool": {
                        "must": [
                            {
                                "range": {
                                    "created_at": {
                                        "gte": start_date.isoformat(),
                                        "lte": now.isoformat()
                                    }
                                }
                            }
                        ],
                        "filter": [
                            {"term": {"is_public": True}}
                        ]
                    }
                },
                "sort": [
                    {"like_count": {"order": "desc"}},
                    {"comment_count": {"order": "desc"}},
                    {"created_at": {"order": "desc"}}
                ],
                "size": limit
            }

            response = await self.es_client.search(
                index="posts",
                body=search_body
            )

            hits = response["hits"]["hits"]
            
            popular_posts = []
            for hit in hits:
                source = hit["_source"]
                post = {
                    "id": hit["_id"],
                    "content": source.get("content"),
                    "user_id": source.get("user_id"),
                    "like_count": source.get("like_count", 0),
                    "comment_count": source.get("comment_count", 0),
                    "created_at": source.get("created_at"),
                    "user": source.get("user")
                }
                popular_posts.append(post)

            return popular_posts

        except Exception as e:
            logger.error(f"Error getting popular posts: {e}")
            return []

    async def bulk_index_posts(self, posts: List[Post], users: Dict[int, User] = None):
        """Bulk index multiple posts"""
        if not await self.is_available():
            return

        try:
            bulk_operations = []
            
            for post in posts:
                post_data = {
                    "id": post.id,
                    "user_id": post.user_id,
                    "content": post.content,
                    "media_url": post.media_url,
                    "media_type": post.media_type,
                    "is_public": post.is_public,
                    "location": post.location,
                    "like_count": post.like_count,
                    "comment_count": post.comment_count,
                    "created_at": post.created_at.isoformat() if post.created_at else None,
                    "updated_at": post.updated_at.isoformat() if post.updated_at else None
                }

                if users and post.user_id in users:
                    user = users[post.user_id]
                    post_data["user"] = {
                        "id": user.id,
                        "username": user.username,
                        "full_name": user.full_name,
                        "profile_picture": user.profile_picture
                    }

                bulk_operations.append({"index": {"_index": "posts", "_id": post.id}})
                bulk_operations.append(post_data)

            if bulk_operations:
                await self.es_client.bulk(
                    body=bulk_operations,
                    refresh=True
                )
                
                logger.info(f"Bulk indexed {len(posts)} posts")

        except Exception as e:
            logger.error(f"Error bulk indexing posts: {e}")

    async def reindex_all_posts(self, db_session):
        """Reindex all posts from database"""
        if not await self.is_available():
            return

        try:
            from sqlalchemy import select
            from sqlalchemy.orm import selectinload
            
            # Get all posts with users
            stmt = select(Post).options(selectinload(Post.user)).where(Post.is_public == True)
            result = await db_session.execute(stmt)
            posts = result.scalars().all()

            # Group users by ID
            users_dict = {}
            for post in posts:
                if post.user and post.user.id not in users_dict:
                    users_dict[post.user.id] = post.user

            await self.bulk_index_posts(posts, users_dict)
            
            logger.info(f"Reindexed {len(posts)} posts")

        except Exception as e:
            logger.error(f"Error reindexing posts: {e}")

    async def get_index_stats(self) -> Dict[str, Any]:
        """Get Elasticsearch index statistics"""
        if not await self.is_available():
            return {}

        try:
            indices = ["posts", "users", "comments"]
            stats = {}

            for index in indices:
                try:
                    index_stats = await self.es_client.indices.stats(index=index)
                    if index in index_stats["indices"]:
                        stats[index] = {
                            "doc_count": index_stats["indices"][index]["total"]["docs"]["count"],
                            "size": index_stats["indices"][index]["total"]["store"]["size_in_bytes"]
                        }
                except Exception as e:
                    logger.error(f"Error getting stats for index {index}: {e}")
                    stats[index] = {"error": str(e)}

            return stats

        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {}

    async def close(self):
        """Close Elasticsearch connection"""
        if self.es_client:
            await self.es_client.close()
            logger.info("Elasticsearch client closed")

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Create a global search service instance
search_service = SearchService()