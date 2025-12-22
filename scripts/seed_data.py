#!/usr/bin/env python3
"""
Seed data script for development and testing
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
import random

# Add the app directory to the Python path
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.insert(0, str(root_dir))

async def seed_users(count: int = 10) -> list:
    """Seed users"""
    from app.db.session import get_db
    from app.models.user import User
    from app.services.auth_service import AuthService
    from sqlalchemy import select
    
    print(f"👥 Seeding {count} users...")
    
    users = []
    first_names = ["John", "Jane", "Bob", "Alice", "Charlie", "Diana", "Eve", "Frank", "Grace", "Henry"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]
    professions = ["Developer", "Designer", "Manager", "Engineer", "Artist", "Writer", "Teacher", "Doctor", "Analyst", "Consultant"]
    
    async for db in get_db():
        auth_service = AuthService(db)
        
        for i in range(count):
            first = random.choice(first_names)
            last = random.choice(last_names)
            profession = random.choice(professions)
            
            user_data = {
                "username": f"{first.lower()}_{last.lower()}_{i}",
                "email": f"{first.lower()}.{last.lower()}{i}@example.com",
                "password": "Password123!",
                "full_name": f"{first} {last}",
                "bio": f"{profession} with {random.randint(1, 20)} years of experience",
                "profile_picture": f"https://i.pravatar.cc/150?img={random.randint(1, 70)}"
            }
            
            try:
                # Check if user exists
                stmt = select(User).where(User.username == user_data["username"])
                result = await db.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if not existing:
                    user = await auth_service.create_user(**user_data)
                    users.append(user)
                    
                    # Update counts
                    user.followers_count = random.randint(0, 1000)
                    user.following_count = random.randint(0, 500)
                    user.posts_count = random.randint(0, 200)
                    
                    await db.commit()
                    
            except Exception as e:
                await db.rollback()
                print(f"⚠️  Error creating user {user_data['username']}: {e}")
    
    print(f"✅ Created {len(users)} users")
    return users

async def seed_posts(users: list, count_per_user: int = 5) -> list:
    """Seed posts"""
    from app.db.session import get_db
    from app.models.post import Post
    from sqlalchemy import select
    
    print(f"📝 Seeding posts ({count_per_user} per user)...")
    
    posts = []
    contents = [
        "Just had the best coffee ever! ☕",
        "Working on an exciting new project! 🚀",
        "Beautiful sunset today! 🌅",
        "Learning new technologies is always fun! 💻",
        "Weekend vibes! 🎉",
        "Just finished reading an amazing book! 📚",
        "Morning workout complete! 💪",
        "Cooking dinner for friends tonight! 👨‍🍳",
        "Travel plans for next month! ✈️",
        "Great meeting with the team today! 👥"
    ]
    
    locations = ["New York", "London", "Tokyo", "Paris", "Sydney", "Berlin", "Toronto", "Singapore", "Dubai", "San Francisco"]
    
    async for db in get_db():
        for user in users:
            for i in range(count_per_user):
                # Random date within last 30 days
                days_ago = random.randint(0, 30)
                created_at = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))
                
                post = Post(
                    user_id=user.id,
                    content=random.choice(contents),
                    media_url=f"https://picsum.photos/800/600?random={random.randint(1, 1000)}" if random.random() > 0.5 else None,
                    media_type="image" if random.random() > 0.5 else None,
                    is_public=True if random.random() > 0.2 else False,
                    location=random.choice(locations) if random.random() > 0.3 else None,
                    like_count=random.randint(0, 500),
                    comment_count=random.randint(0, 100),
                    share_count=random.randint(0, 50),
                    created_at=created_at,
                    updated_at=created_at
                )
                
                db.add(post)
                posts.append(post)
        
        try:
            await db.commit()
            print(f"✅ Created {len(posts)} posts")
        except Exception as e:
            await db.rollback()
            print(f"⚠️  Error creating posts: {e}")
    
    return posts

async def seed_comments(users: list, posts: list, count_per_post: int = 3) -> list:
    """Seed comments"""
    from app.db.session import get_db
    from app.models.comment import Comment
    
    print(f"💬 Seeding comments ({count_per_post} per post)...")
    
    comments = []
    comment_texts = [
        "Great post! 👍",
        "I completely agree!",
        "Thanks for sharing!",
        "This is amazing!",
        "Very insightful!",
        "Looking forward to more!",
        "Well said!",
        "Keep up the good work!",
        "Interesting perspective!",
        "Thanks for the inspiration!"
    ]
    
    async for db in get_db():
        for post in posts:
            post_comments = []
            for i in range(count_per_post):
                commenter = random.choice(users)
                days_ago = random.randint(0, 30)
                created_at = post.created_at + timedelta(days=random.randint(0, days_ago), hours=random.randint(0, 23))
                
                # Decide if this is a reply to another comment
                parent_id = None
                if post_comments and random.random() > 0.7:
                    parent_id = random.choice(post_comments).id
                
                comment = Comment(
                    post_id=post.id,
                    user_id=commenter.id,
                    content=random.choice(comment_texts),
                    parent_id=parent_id,
                    like_count=random.randint(0, 50),
                    created_at=created_at,
                    updated_at=created_at
                )
                
                db.add(comment)
                comments.append(comment)
                post_comments.append(comment)
        
        try:
            await db.commit()
            print(f"✅ Created {len(comments)} comments")
        except Exception as e:
            await db.rollback()
            print(f"⚠️  Error creating comments: {e}")
    
    return comments

async def seed_likes(users: list, posts: list, comments: list) -> None:
    """Seed likes for posts and comments"""
    from app.db.session import get_db
    from app.models.like import Like
    
    print("❤️  Seeding likes...")
    
    async for db in get_db():
        like_count = 0
        
        # Like posts
        for post in posts:
            # Random subset of users like this post
            likers = random.sample(users, min(random.randint(0, len(users) // 2), len(users)))
            
            for liker in likers:
                days_ago = random.randint(0, 30)
                created_at = post.created_at + timedelta(days=random.randint(0, days_ago), hours=random.randint(0, 23))
                
                like = Like(
                    user_id=liker.id,
                    post_id=post.id,
                    like_type="post",
                    created_at=created_at,
                    updated_at=created_at
                )
                
                db.add(like)
                like_count += 1
        
        # Like comments
        for comment in comments:
            # Random subset of users like this comment
            likers = random.sample(users, min(random.randint(0, len(users) // 4), len(users)))
            
            for liker in likers:
                days_ago = random.randint(0, 30)
                created_at = comment.created_at + timedelta(days=random.randint(0, days_ago), hours=random.randint(0, 23))
                
                like = Like(
                    user_id=liker.id,
                    comment_id=comment.id,
                    like_type="comment",
                    created_at=created_at,
                    updated_at=created_at
                )
                
                db.add(like)
                like_count += 1
        
        try:
            await db.commit()
            print(f"✅ Created {like_count} likes")
        except Exception as e:
            await db.rollback()
            print(f"⚠️  Error creating likes: {e}")

async def seed_follows(users: list) -> None:
    """Seed follow relationships"""
    from app.db.session import get_db
    from app.models.follow import Follow
    
    print("👥 Seeding follow relationships...")
    
    async for db in get_db():
        follow_count = 0
        
        for user in users:
            # Each user follows random other users
            other_users = [u for u in users if u.id != user.id]
            following = random.sample(other_users, min(random.randint(0, len(other_users) // 3), len(other_users)))
            
            for followed_user in following:
                days_ago = random.randint(0, 90)
                created_at = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))
                
                follow = Follow(
                    follower_id=user.id,
                    following_id=followed_user.id,
                    created_at=created_at,
                    updated_at=created_at
                )
                
                db.add(follow)
                follow_count += 1
        
        try:
            await db.commit()
            print(f"✅ Created {follow_count} follow relationships")
            
            # Update user counts
            from sqlalchemy import update, and_
            
            # Update followers count
            for user in users:
                followers_stmt = (
                    update(User)
                    .where(User.id == user.id)
                    .values(followers_count=(
                        select(func.count())
                        .where(Follow.following_id == user.id)
                        .scalar_subquery()
                    ))
                )
                await db.execute(followers_stmt)
            
            # Update following count
            for user in users:
                following_stmt = (
                    update(User)
                    .where(User.id == user.id)
                    .values(following_count=(
                        select(func.count())
                        .where(Follow.follower_id == user.id)
                        .scalar_subquery()
                    ))
                )
                await db.execute(following_stmt)
            
            await db.commit()
            
        except Exception as e:
            await db.rollback()
            print(f"⚠️  Error creating follows: {e}")

async def seed_all() -> None:
    """Seed all data"""
    print("🌱 Starting database seeding...")
    
    # Seed users
    users = await seed_users(20)
    
    # Seed posts
    posts = await seed_posts(users, 3)
    
    # Seed comments
    comments = await seed_comments(users, posts, 2)
    
    # Seed likes
    await seed_likes(users, posts, comments)
    
    # Seed follows
    await seed_follows(users)
    
    print("🎉 Database seeding completed!")

async def seed_test_data() -> None:
    """Seed minimal data for testing"""
    print("🧪 Seeding test data...")
    
    from app.db.session import get_db
    from app.models.user import User
    from app.services.auth_service import AuthService
    from sqlalchemy import select
    
    async for db in get_db():
        auth_service = AuthService(db)
        
        # Create test users
        test_users = [
            {"username": "test1", "email": "test1@example.com", "password": "Test123!"},
            {"username": "test2", "email": "test2@example.com", "password": "Test123!"},
            {"username": "test3", "email": "test3@example.com", "password": "Test123!"},
        ]
        
        users = []
        for user_data in test_users:
            stmt = select(User).where(User.username == user_data["username"])
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if not existing:
                user = await auth_service.create_user(**user_data)
                users.append(user)
        
        await db.commit()
    
    print("✅ Test data seeded")

async def clear_all_data(confirm: bool = False) -> None:
    """Clear all seed data"""
    if not confirm:
        print("⚠️  WARNING: This will delete ALL data from the database!")
        print("   Use --confirm flag to proceed")
        return
    
    from app.db.session import engine
    from sqlalchemy import text
    
    tables = [
        "likes", "follows", "comments", "posts", "notifications", "users"
    ]
    
    print("🧹 Clearing all data...")
    
    async with engine.begin() as conn:
        # Disable foreign key constraints (for SQLite)
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        
        for table in tables:
            try:
                await conn.execute(text(f"DELETE FROM {table}"))
                print(f"  Cleared {table}")
            except:
                pass  # Table might not exist
        
        # Re-enable foreign key constraints
        await conn.execute(text("PRAGMA foreign_keys = ON"))
    
    print("✅ All data cleared")

def main() -> None:
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Seeding")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Seed all command
    subparsers.add_parser("all", help="Seed all data")
    
    # Seed users command
    users_parser = subparsers.add_parser("users", help="Seed users only")
    users_parser.add_argument("--count", type=int, default=10, help="Number of users")
    
    # Seed test command
    subparsers.add_parser("test", help="Seed test data")
    
    # Clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all data")
    clear_parser.add_argument("--confirm", action="store_true", help="Confirm clear")
    
    # Reset command
    reset_parser = subparsers.add_parser("reset", help="Clear and reseed")
    reset_parser.add_argument("--confirm", action="store_true", help="Confirm reset")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        if args.command == "all":
            asyncio.run(seed_all())
            
        elif args.command == "users":
            asyncio.run(seed_users(args.count))
            
        elif args.command == "test":
            asyncio.run(seed_test_data())
            
        elif args.command == "clear":
            asyncio.run(clear_all_data(args.confirm))
            
        elif args.command == "reset":
            if not args.confirm:
                print("⚠️  WARNING: This will delete ALL data from the database!")
                print("   Use --confirm flag to proceed")
                return
            
            asyncio.run(clear_all_data(True))
            asyncio.run(seed_all())
            
    except KeyboardInterrupt:
        print("\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()