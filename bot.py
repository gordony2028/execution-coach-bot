# Complete Execution Coach Bot with Gemini AI Integration
# Requirements: python-telegram-bot, sqlalchemy, python-dotenv, apscheduler, google-generativeai

import os
import json
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, NoReturn

import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, Boolean, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncio

# Database Models
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String(50))
    first_name = Column(String(50))
    current_business_idea = Column(Text)
    execution_phase = Column(String(20), default='planning')  # planning, validation, mvp, traction
    created_at = Column(DateTime, default=datetime.utcnow)
    timezone = Column(String(50), default='UTC')
    preferred_checkin_time = Column(String(5), default='18:00')
    total_activities = Column(Integer, default=0)
    last_active = Column(DateTime, default=datetime.utcnow)

class Goal(Base):
    __tablename__ = 'goals'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text)
    target_date = Column(DateTime)
    status = Column(String(20), default='active')  # active, completed, paused
    created_at = Column(DateTime, default=datetime.utcnow)
    goal_type = Column(String(20))  # weekly, monthly, milestone
    priority = Column(Integer, default=1)

class Activity(Base):
    __tablename__ = 'activities'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    goal_id = Column(Integer)
    description = Column(Text, nullable=False)
    activity_type = Column(String(50))  # task_completed, milestone_reached, learning, blocker, win, struggle
    timestamp = Column(DateTime, default=datetime.utcnow)
    mood_score = Column(Integer)  # 1-5 energy/motivation level
    notes = Column(Text)
    context_tags = Column(String(200))  # procrastination, impatience, breakthrough, etc.

class Progress(Base):
    __tablename__ = 'progress'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    metric_name = Column(String(100))  # customers_contacted, revenue, users_signed_up
    metric_value = Column(Float)
    date_recorded = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)

class Conversation(Base):
    __tablename__ = 'conversations'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, nullable=False)
    message_text = Column(Text)
    bot_response = Column(Text)
    context_tags = Column(String(200))  # procrastination, impatience, stuck, win
    timestamp = Column(DateTime, default=datetime.utcnow)
    response_type = Column(String(50))  # gemini, fallback, command

# Render-specific configuration
class RenderConfig:
    def __init__(self):
        self.PORT = int(os.getenv('PORT', 10000))
        self.TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
        self.DATABASE_URL = os.getenv('DATABASE_URL')
        self.GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
        
        # Render provides DATABASE_URL in specific format
        if self.DATABASE_URL and self.DATABASE_URL.startswith('postgres://'):
            # Convert postgres:// to postgresql:// for SQLAlchemy compatibility
            self.DATABASE_URL = self.DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    
    def validate(self):
        if not self.TELEGRAM_TOKEN:
            print("❌ TELEGRAM_TOKEN not found in environment variables")
            print("Please set it in Render dashboard")
            sys.exit(1)
        
        if not self.DATABASE_URL:
            print("❌ DATABASE_URL not found")
            print("Ensure database is created and connected")
            sys.exit(1)
            
        if not self.GEMINI_API_KEY:
            print("⚠️  GEMINI_API_KEY not found - using fallback responses")
            print("Add Gemini API key for enhanced AI coaching")
        
        print("✅ Configuration validated")
        return True

# Graceful shutdown for Render
def signal_handler(signum, frame):
    print(f"🛑 Received signal {signum}. Shutting down gracefully...")
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Database Setup
class DatabaseManager:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True, pool_recycle=300)
        
        # Handle schema migration for BigInteger telegram_id
        self.migrate_schema()
        
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
    
    def migrate_schema(self):
        """Handle schema migration for BigInteger telegram_id"""
        try:
            # Check if we need to migrate by trying to create a test user
            # If it fails with integer out of range, we need to drop and recreate tables
            with self.engine.connect() as conn:
                # Check if tables exist and if telegram_id column is the right type
                result = conn.execute("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'telegram_id'
                """)
                
                row = result.fetchone()
                if row and 'integer' in row[1] and 'bigint' not in row[1]:
                    print("🔄 Migrating database schema for BigInteger telegram_id...")
                    
                    # Drop existing tables to recreate with correct schema
                    Base.metadata.drop_all(self.engine)
                    print("✅ Old tables dropped, recreating with BigInteger support...")
                    
        except Exception as e:
            print(f"ℹ️ Schema migration check: {e}")
            # If there's an error, it's likely the tables don't exist yet, which is fine
    
    def get_session(self) -> Session:
        return self.SessionLocal()
    
    def get_or_create_user(self, telegram_user) -> User:
        session = self.get_session()
        try:
            user = session.query(User).filter_by(telegram_id=telegram_user.id).first()
            if not user:
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    first_name=telegram_user.first_name
                )
                session.add(user)
                session.commit()
                session.refresh(user)
            else:
                # Update last active
                user.last_active = datetime.utcnow()
                session.commit()
            return user
        finally:
            session.close()

# Context Manager for User State
class UserContext:
    def __init__(self, db_manager: DatabaseManager, user_id: int):
        self.db = db_manager
        self.user_id = user_id
        self._user_data = None
    
    def get_user_data(self) -> Dict:
        if self._user_data is None:
            session = self.db.get_session()
            try:
                user = session.query(User).filter_by(telegram_id=self.user_id).first()
                if not user:
                    return {}
                    
                recent_activities = session.query(Activity).filter_by(
                    user_id=self.user_id
                ).order_by(Activity.timestamp.desc()).limit(20).all()
                
                active_goals = session.query(Goal).filter_by(
                    user_id=self.user_id, status='active'
                ).order_by(Goal.priority.desc()).all()
                
                recent_conversations = session.query(Conversation).filter_by(
                    user_id=self.user_id
                ).order_by(Conversation.timestamp.desc()).limit(10).all()
                
                self._user_data = {
                    'user': user,
                    'recent_activities': recent_activities,
                    'active_goals': active_goals,
                    'recent_conversations': recent_conversations,
                    'last_checkin': self.get_last_checkin(),
                    'current_streak': self.calculate_streak(),
                    'execution_phase': user.execution_phase,
                    'total_activities': user.total_activities,
                    'days_since_start': (datetime.utcnow() - user.created_at).days
                }
            finally:
                session.close()
        return self._user_data
    
    def get_last_checkin(self) -> Optional[datetime]:
        session = self.db.get_session()
        try:
            last_activity = session.query(Activity).filter_by(
                user_id=self.user_id
            ).order_by(Activity.timestamp.desc()).first()
            return last_activity.timestamp if last_activity else None
        finally:
            session.close()
    
    def calculate_streak(self) -> int:
        session = self.db.get_session()
        try:
            # Calculate consecutive days with activity
            activities = session.query(Activity).filter_by(
                user_id=self.user_id
            ).order_by(Activity.timestamp.desc()).all()
            
            if not activities:
                return 0
            
            streak = 0
            current_date = datetime.now().date()
            
            # Group activities by date
            activity_dates = set()
            for activity in activities:
                activity_dates.add(activity.timestamp.date())
            
            # Count consecutive days
            check_date = current_date
            while check_date in activity_dates:
                streak += 1
                check_date = check_date - timedelta(days=1)
            
            return streak
        finally:
            session.close()
    
    def log_activity(self, description: str, activity_type: str, mood_score: int = None, notes: str = None, context_tags: str = None):
        session = self.db.get_session()
        try:
            activity = Activity(
                user_id=self.user_id,
                description=description,
                activity_type=activity_type,
                mood_score=mood_score,
                notes=notes,
                context_tags=context_tags
            )
            session.add(activity)
            
            # Update user total activities
            user = session.query(User).filter_by(telegram_id=self.user_id).first()
            if user:
                user.total_activities = (user.total_activities or 0) + 1
                user.last_active = datetime.utcnow()
            
            session.commit()
            self._user_data = None  # Reset cache
        finally:
            session.close()

# Gemini AI Integration with Specialized Agents
class GeminiCoach:
    def __init__(self, api_key: str = None):
        self.api_key = api_key
        
        print(f"🔑 Gemini API Key provided: {'Yes' if api_key else 'No'}")
        if api_key:
            print(f"🔑 API Key length: {len(api_key)} characters")
            print(f"🔑 API Key starts with: {api_key[:10]}...")
        
        if api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-pro')
                self.enabled = True
                print("✅ Gemini AI configured successfully")
            except Exception as e:
                print(f"❌ Gemini AI configuration failed: {e}")
                self.enabled = False
                self.model = None
        else:
            self.enabled = False
            self.model = None
            print("⚠️ Gemini AI disabled - no API key provided")
        
        # Load specialized agent prompts
        self.load_specialized_prompts()
    
    def load_specialized_prompts(self):
        """Load the specialized agent prompts"""
        
        self.business_ideas_prompt = """
# Creative Business Ideas Agent

You are an innovative business strategist and creative thinker whose specialty is generating unique, viable business ideas. Your goal is to help entrepreneurs discover opportunities they might not have considered.

## Your Approach

**Be Creative Yet Practical**: Generate ideas that are both imaginative and realistically executable. Balance innovation with market viability.

**Think Across Industries**: Draw inspiration from diverse sectors, emerging technologies, changing consumer behaviors, and societal trends.

**Consider Different Business Models**: Include traditional businesses, digital services, subscription models, marketplaces, SaaS, physical products, and hybrid approaches.

## When Generating Ideas

1. **Start with the "why"** - Identify a real problem or unmet need
2. **Explain the opportunity** - Why this idea could succeed now
3. **Suggest implementation approach** - High-level steps to get started
4. **Note potential challenges** - Be honest about obstacles
5. **Estimate resources needed** - Rough idea of startup requirements

## Response Format

For each business idea, provide:

**Idea Name**: [Catchy, descriptive name]
**The Problem**: What specific issue does this solve?
**The Solution**: Your business concept in 2-3 sentences
**Why Now**: What makes this timely/relevant?
**Getting Started**: 3-4 initial steps
**Investment Level**: Low/Medium/High and rough dollar range
**Potential Challenges**: 2-3 main obstacles to consider

Generate 3-5 distinct business ideas unless requested otherwise. Make each idea substantively different from the others.
        """
        
        self.market_research_prompt = """
# Market Research & Analysis Agent

You are an expert market research analyst with deep expertise in industry analysis, competitive intelligence, and market opportunity assessment. Your role is to provide comprehensive, data-driven insights that inform strategic business decisions.

## Research Methodology

### Analysis Framework
1. **Market Overview**: Size, growth rate, key segments
2. **Competitive Landscape**: Major players and competitive dynamics  
3. **Customer Analysis**: Target segments and behavior patterns
4. **Trends & Drivers**: Forces shaping the market
5. **Opportunities & Threats**: SWOT-style analysis
6. **Recommendations**: Actionable strategic insights

### Competitive Analysis Format
**Company Name**: [Competitor]
- **Market Position**: Market share and positioning
- **Value Proposition**: Key differentiators and messaging
- **Product/Service Portfolio**: Core offerings and pricing
- **Strengths**: Competitive advantages
- **Weaknesses**: Vulnerabilities and gaps
- **Strategy**: Go-to-market approach and recent moves

## Output Guidelines

### Be Data-Driven
- Provide quantitative metrics where possible
- Include relevant market size estimates
- Distinguish between facts and assumptions

### Think Strategically  
- Connect findings to business implications
- Identify patterns and underlying drivers
- Provide actionable recommendations

Provide structured, professional market research similar to what you'd get from a consulting firm.
        """
        
        self.execution_coach_prompt = """
# Solo Entrepreneur Execution Coach

You are a specialized execution coach for solo entrepreneurs who struggle with procrastination, impatience for results, and resource constraints. Your mission is to break through execution barriers and build momentum through strategic, lean action-taking.

## Core Philosophy

**Start Ugly, Iterate Fast**: Perfect is the enemy of done. Focus on getting something launched, then improve.

**Micro-Progress Beats Perfect Plans**: Small, consistent actions compound faster than waiting for the "right" moment.

**Validation Over Investment**: Prove demand before spending money, time, or energy scaling.

**Build While You Bootstrap**: Create credibility and track record through executed projects, not just ideas.

## Focus Areas

### Procrastination Breakthrough
- Break tasks into 5-minute actions
- Create momentum triggers
- Use accountability systems

### Patience & Expectation Management  
- Set realistic timeline expectations
- Identify early wins and leading indicators
- Focus on progress over perfection

### Resource-Efficient Execution
- Zero-budget MVP strategies
- Time-leverage techniques
- Bootstrap validation methods

### Credibility Building
- Document every small win
- Build social proof through action
- Create demonstrable track record

Always provide immediate, actionable advice that accounts for being a solo entrepreneur with limited resources.
        """

    async def generate_business_ideas(self, context_data: Dict, user_request: str = "") -> str:
        """Generate business ideas using specialized prompt"""
        if not self.enabled:
            return "💡 Gemini AI not available. Please add your API key for business idea generation."
        
        user = context_data.get('user')
        current_idea = user.current_business_idea if user else None
        phase = context_data.get('execution_phase', 'planning')
        
        full_prompt = f"""
{self.business_ideas_prompt}

## Current Context:
- User's current business idea: {current_idea or 'None set'}
- Execution phase: {phase}
- User request: {user_request or 'Generate creative business ideas'}

Based on this context, provide 3-5 creative business ideas that would be suitable for a solo entrepreneur with limited resources. Focus on ideas that can be started small and validated quickly.
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text.strip() if response and response.text else "Unable to generate ideas at the moment."
        except Exception as e:
            print(f"Business ideas generation error: {e}")
            return "Unable to generate ideas at the moment. Please try again later."
    
    async def conduct_market_research(self, context_data: Dict, research_topic: str) -> str:
        """Conduct market research using specialized prompt"""
        if not self.enabled:
            return "📊 Gemini AI not available. Please add your API key for market research."
        
        user = context_data.get('user')
        current_idea = user.current_business_idea if user else None
        phase = context_data.get('execution_phase', 'planning')
        
        full_prompt = f"""
{self.market_research_prompt}

## Research Request:
- Topic: {research_topic}
- User's business context: {current_idea or 'General research'}
- Current phase: {phase}

Provide a comprehensive market research analysis for this topic. Include market size estimates, key competitors, target customers, trends, and strategic recommendations. Keep the analysis practical for a solo entrepreneur.
        """
        
        try:
            response = await asyncio.to_thread(self.model.generate_content, full_prompt)
            return response.text.strip() if response and response.text else "Unable to complete research at the moment."
        except Exception as e:
            print(f"Market research error: {e}")
            return "Unable to complete research at the moment. Please try again later."

    def create_coaching_prompt(self, message: str, context_data: Dict) -> str:
        """Create a comprehensive prompt for Gemini based on user context"""
        
        user = context_data.get('user')
        recent_activities = context_data.get('recent_activities', [])
        active_goals = context_data.get('active_goals', [])
        streak = context_data.get('current_streak', 0)
        phase = context_data.get('execution_phase', 'planning')
        total_activities = context_data.get('total_activities', 0)
        days_since_start = context_data.get('days_since_start', 0)
        
        # Build context summary
        activities_summary = ""
        if recent_activities:
            activities_summary = "Recent activities:\n"
            for activity in recent_activities[:5]:
                activities_summary += f"- {activity.description} ({activity.activity_type})\n"
        
        goals_summary = ""
        if active_goals:
            goals_summary = "Current goals:\n"
            for goal in active_goals:
                goals_summary += f"- {goal.title} (due: {goal.target_date})\n"
        
        business_context = f"Business idea: {user.current_business_idea}" if user and user.current_business_idea else "No business idea set yet"
        
        full_prompt = f"""
{self.execution_coach_prompt}

## USER CONTEXT:
- Name: {user.first_name if user else 'User'}
- {business_context}
- Execution phase: {phase}
- Days using coach: {days_since_start}
- Current streak: {streak} days
- Total actions taken: {total_activities}

{activities_summary}

{goals_summary}

## USER MESSAGE: "{message}"

## COACHING GUIDELINES:
- Be encouraging but realistic
- Reference their specific history and patterns
- Give concrete, actionable advice
- Keep responses under 200 words
- Use emojis sparingly but effectively
- Address their specific challenges (procrastination, impatience, resource constraints)
- Acknowledge progress and patterns you notice
- If they're stuck, suggest a 5-minute micro-action
- If they're impatient, remind them of realistic timelines for solo entrepreneurs
- If they achieved something, celebrate and ask what they learned

Provide a personalized coaching response that shows you understand their journey and current situation.
        """
        return full_prompt
    
    async def generate_response(self, message: str, context_data: Dict) -> str:
        """Generate AI-powered coaching response"""
        
        # Debug logging
        print(f"🤖 Gemini AI enabled: {self.enabled}")
        print(f"📝 User message: {message[:50]}...")
        
        if not self.enabled:
            print("⚠️ Gemini AI not enabled, using fallback")
            return self.fallback_response(message, context_data)
        
        try:
            print("🔄 Creating coaching prompt...")
            prompt = self.create_coaching_prompt(message, context_data)
            print(f"📋 Prompt length: {len(prompt)} characters")
            
            print("🌐 Calling Gemini API...")
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            print(f"📨 Gemini response received: {bool(response)}")
            
            if response and response.text:
                response_text = response.text.strip()
                print(f"✅ Gemini response length: {len(response_text)} characters")
                print(f"🎯 First 100 chars: {response_text[:100]}...")
                return response_text
            else:
                print("❌ Gemini response empty or invalid")
                return self.fallback_response(message, context_data)
                
        except Exception as e:
            print(f"⚠️ Gemini API error: {e}")
            print(f"🔍 Error type: {type(e).__name__}")
            return self.fallback_response(message, context_data)
    
    def fallback_response(self, message: str, context_data: Dict) -> str:
        """Fallback responses when Gemini is unavailable"""
        user = context_data.get('user')
        streak = context_data.get('current_streak', 0)
        phase = context_data.get('execution_phase', 'planning')
        
        message_lower = message.lower()
        
        # Procrastination responses
        if any(word in message_lower for word in ['procrastinating', 'avoiding', 'stuck', 'overwhelmed', 'can\'t start']):
            return f"I see you're feeling stuck, {user.first_name if user else 'friend'}. Your {streak}-day streak shows you CAN take action! Let's break this down: what's the smallest possible step you could take in the next 5 minutes? Even tiny progress in the {phase} phase builds momentum. 🚀"
        
        # Impatience responses
        if any(word in message_lower for word in ['slow', 'not working', 'no results', 'giving up', 'frustrated']):
            return f"I understand the frustration! In the {phase} phase, most solo entrepreneurs need 3-6 months to see real results. Your {streak}-day action streak is exactly how success builds - one step at a time. What would count as progress in the next 7 days? 📈"
        
        # Celebration responses
        if any(word in message_lower for word in ['completed', 'finished', 'done', 'achieved', 'launched', 'win']):
            return f"🎉 Amazing work! That's day {streak + 1} of taking action. This is exactly how momentum builds in the {phase} phase. What felt good about completing that? And what's the next small step to keep this energy going? 💪"
        
        # General coaching
        return f"I'm here to help you execute, {user.first_name if user else 'friend'}! You're in the {phase} phase with a {streak}-day action streak. What's on your mind? Use /stuck if you're procrastinating, /win to celebrate progress, or just tell me what you're working on! 🎯"

# Bot Implementation
class ExecutionCoachBot:
    def __init__(self, token: str, database_url: str, gemini_api_key: str = None):
        self.db = DatabaseManager(database_url)
        self.app = Application.builder().token(token).build()
        self.scheduler = AsyncIOScheduler()
        self.gemini_coach = GeminiCoach(gemini_api_key)
        self.setup_handlers()
        self.setup_scheduler()
    
    def setup_handlers(self):
        # Commands
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("plan", self.weekly_planning))
        self.app.add_handler(CommandHandler("progress", self.show_progress))
        self.app.add_handler(CommandHandler("stuck", self.handle_stuck))
        self.app.add_handler(CommandHandler("win", self.log_win))
        self.app.add_handler(CommandHandler("goal", self.set_goal))
        self.app.add_handler(CommandHandler("phase", self.set_phase))
        self.app.add_handler(CommandHandler("idea", self.set_business_idea))
        
        # Specialized Agent Commands
        self.app.add_handler(CommandHandler("ideas", self.generate_business_ideas_command))
        self.app.add_handler(CommandHandler("research", self.market_research_command))
        self.app.add_handler(CommandHandler("modes", self.show_agent_modes))
        
        # Debug Commands
        self.app.add_handler(CommandHandler("test", self.test_gemini))
        self.app.add_handler(CommandHandler("debug", self.debug_info))
        
        # Message handlers
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))
    
    def setup_scheduler(self):
        # Daily check-ins at 6 PM
        self.scheduler.add_job(
            self.daily_checkin,
            CronTrigger(hour=18, minute=0),
            id='daily_checkin'
        )
        
        # Weekly planning reminder on Sunday at 10 AM
        self.scheduler.add_job(
            self.weekly_planning_reminder,
            CronTrigger(day_of_week='sun', hour=10, minute=0),
            id='weekly_planning'
        )
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = self.db.get_or_create_user(update.effective_user)
        
        welcome_msg = f"""
🚀 Welcome to your AI Execution Coach, {user.first_name}!

I'm powered by advanced AI and have **3 specialized modes** to help you succeed as a solo entrepreneur:

**🎯 EXECUTION COACH** (Default Mode)
• Daily accountability and check-ins  
• Breaking down overwhelming tasks into 5-minute actions
• Celebrating wins and building streaks
• Managing expectations with realistic timelines
• Getting unstuck when procrastinating

**💡 BUSINESS IDEAS GENERATOR**
• Creative, viable business concepts
• Market opportunity analysis
• Implementation roadmaps

**📊 MARKET RESEARCHER**  
• Competitive analysis
• Industry insights
• Customer research

**Quick Setup Commands:**
/idea - Set your current business idea
/phase - Set execution phase (planning/validation/mvp/traction)  
/goal - Set a goal with deadline

**Daily Commands:**
/stuck - Get immediate help when procrastinating
/win - Log any victory to build momentum
/progress - See your streaks and patterns
/plan - Weekly planning session

**Specialized Agents:**
/ideas - Generate creative business ideas
/research [topic] - Conduct market research
/modes - See all available agent modes

Let's start! What's your current business idea or project?
        """
        
        await update.message.reply_text(welcome_msg)
    
    async def set_business_idea(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.args:
            idea = ' '.join(context.args)
            session = self.db.get_session()
            try:
                user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
                if user:
                    user.current_business_idea = idea
                    session.commit()
                    await update.message.reply_text(f"💡 Business idea set: {idea}\n\nNow use /phase to set your current execution phase!")
                else:
                    await update.message.reply_text("Please use /start first to initialize your profile.")
            finally:
                session.close()
        else:
            await update.message.reply_text("Usage: /idea Your business idea description")
    
    async def set_phase(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.args:
            phase = context.args[0].lower()
            valid_phases = ['planning', 'validation', 'mvp', 'traction']
            
            if phase in valid_phases:
                session = self.db.get_session()
                try:
                    user = session.query(User).filter_by(telegram_id=update.effective_user.id).first()
                    if user:
                        user.execution_phase = phase
                        session.commit()
                        await update.message.reply_text(f"📊 Execution phase set to: {phase.upper()}\n\nGreat! Now I can give you phase-specific coaching. What are you working on today?")
                    else:
                        await update.message.reply_text("Please use /start first to initialize your profile.")
                finally:
                    session.close()
            else:
                await update.message.reply_text(f"Valid phases: {', '.join(valid_phases)}")
        else:
            await update.message.reply_text("Usage: /phase [planning|validation|mvp|traction]")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        message_text = update.message.text
        
        print(f"👤 Message from user {user_id}: {message_text}")
        
        # Ensure user exists
        self.db.get_or_create_user(update.effective_user)
        
        # Get user context
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        # Debug context
        print(f"📊 Context loaded - User: {context_data.get('user', {}).first_name if context_data.get('user') else 'None'}")
        print(f"🔥 Streak: {context_data.get('current_streak', 0)}")
        print(f"🚀 Phase: {context_data.get('execution_phase', 'unknown')}")
        print(f"📈 Activities: {len(context_data.get('recent_activities', []))}")
        
        # Generate AI-powered response
        response = await self.gemini_coach.generate_response(message_text, context_data)
        
        # Determine response type and context tags
        response_type = "gemini" if self.gemini_coach.enabled else "fallback"
        context_tags = self.analyze_message_context(message_text)
        
        print(f"🤖 Response type: {response_type}")
        print(f"📝 Response length: {len(response)} characters")
        
        # Log conversation
        session = self.db.get_session()
        try:
            conversation = Conversation(
                user_id=user_id,
                message_text=message_text,
                bot_response=response,
                context_tags=context_tags,
                response_type=response_type
            )
            session.add(conversation)
            session.commit()
        finally:
            session.close()
        
        await update.message.reply_text(response)
    
    def analyze_message_context(self, message: str) -> str:
        """Analyze message to tag context for future reference"""
        message_lower = message.lower()
        tags = []
        
        if any(word in message_lower for word in ['procrastinating', 'avoiding', 'stuck', 'overwhelmed']):
            tags.append('procrastination')
        
        if any(word in message_lower for word in ['slow', 'frustrated', 'no results', 'impatient']):
            tags.append('impatience')
        
        if any(word in message_lower for word in ['completed', 'finished', 'done', 'win', 'success']):
            tags.append('win')
        
        if any(word in message_lower for word in ['customer', 'client', 'user', 'sale']):
            tags.append('customer_related')
        
        if any(word in message_lower for word in ['money', 'revenue', 'funding', 'investment']):
            tags.append('financial')
        
        return ','.join(tags) if tags else 'general'
    
    async def handle_stuck(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        # Log stuck event
        user_context.log_activity("User reported feeling stuck", "blocker", context_tags="procrastination,stuck")
        
        # Generate specific unstuck response
        unstuck_message = "I'm feeling stuck and procrastinating. Please help me get unstuck with a specific 5-minute action I can take right now."
        response = await self.gemini_coach.generate_response(unstuck_message, context_data)
        
        await update.message.reply_text(f"🚨 Stuck Alert Activated!\n\n{response}")
    
    async def log_win(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        win_description = ' '.join(context.args) if context.args else "Achieved a win!"
        
        user_context = UserContext(self.db, user_id)
        user_context.log_activity(win_description, "win", mood_score=4, context_tags="win,celebration")
        
        context_data = user_context.get_user_data()
        
        celebration_message = f"I just achieved a win: {win_description}. Please celebrate with me and help me build on this momentum!"
        response = await self.gemini_coach.generate_response(celebration_message, context_data)
        
        await update.message.reply_text(f"🎉 Win Logged!\n\n{response}")
    
    async def show_progress(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        user = context_data.get('user')
        streak = context_data.get('current_streak', 0)
        total_activities = context_data.get('total_activities', 0)
        days_since_start = context_data.get('days_since_start', 0)
        recent_activities = context_data.get('recent_activities', [])
        
        progress_msg = f"""
📊 **Your Execution Progress**

🔥 Current streak: **{streak} days**
📈 Total actions: **{total_activities}**
📅 Days as entrepreneur: **{days_since_start}**
🚀 Phase: **{user.execution_phase.upper() if user else 'Not set'}**

**Recent Activities:**
"""
        
        if recent_activities:
            for activity in recent_activities[:5]:
                days_ago = (datetime.utcnow() - activity.timestamp).days
                days_text = "today" if days_ago == 0 else f"{days_ago} days ago"
                progress_msg += f"• {activity.description} ({days_text})\n"
        else:
            progress_msg += "• No recent activities logged\n"
        
        progress_msg += f"\n💪 Keep building momentum! Every action counts."
        
        await update.message.reply_text(progress_msg)

    async def show_agent_modes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        modes_msg = """
🤖 **Available Agent Modes**

**🎯 EXECUTION COACH** (Default)
*Helps with procrastination, goal-setting, and daily accountability*
• Just send any message for coaching
• /stuck - Get unstuck from procrastination
• /win - Log victories and build momentum
• /progress - See your streaks and patterns

**💡 BUSINESS IDEAS GENERATOR**
*Creates innovative, viable business concepts*
• /ideas - Generate 3-5 creative business ideas
• /ideas [theme] - Ideas focused on specific theme
• Examples: `/ideas AI tools` or `/ideas local services`

**📊 MARKET RESEARCHER**  
*Provides competitive analysis and industry insights*
• /research [topic] - Comprehensive market analysis
• Examples: `/research food delivery apps` or `/research fitness wearables`

**📋 PLANNING & GOALS**
• /plan - Weekly planning session
• /goal [description] - Set new goal
• /idea [description] - Set business idea
• /phase [planning|validation|mvp|traction] - Set execution phase

All modes remember your history, goals, and patterns to provide personalized insights! 🧠
        """
        
        await update.message.reply_text(modes_msg)
    
    async def generate_business_ideas_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        # Get user request if provided
        user_request = ' '.join(context.args) if context.args else ""
        
        # Show typing indicator
        await update.message.reply_text("💡 Generating creative business ideas for you... This may take a moment.")
        
        # Generate ideas using specialized prompt
        ideas_response = await self.gemini_coach.generate_business_ideas(context_data, user_request)
        
        # Log this as an activity
        user_context.log_activity("Generated business ideas", "planning", context_tags="business_ideas,brainstorming")
        
        final_response = f"💡 **Creative Business Ideas**\n\n{ideas_response}\n\n💪 Use /research [topic] to analyze any of these ideas further!"
        
        # Split long responses if needed
        if len(final_response) > 4000:
            parts = [final_response[i:i+4000] for i in range(0, len(final_response), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(final_response)
    
    async def test_gemini(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test Gemini AI directly"""
        await update.message.reply_text("🧪 Testing Gemini AI connection...")
        
        if not self.gemini_coach.enabled:
            await update.message.reply_text("❌ Gemini AI not enabled. Check GEMINI_API_KEY environment variable.")
            return
        
        try:
            # Simple test prompt
            test_response = await asyncio.to_thread(
                self.gemini_coach.model.generate_content, 
                "Say 'Hello! Gemini AI is working correctly.' and nothing else."
            )
            
            if test_response and test_response.text:
                await update.message.reply_text(f"✅ Gemini AI Test Result:\n{test_response.text.strip()}")
            else:
                await update.message.reply_text("❌ Gemini AI returned empty response.")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Gemini AI Test Failed:\n{str(e)}")
    
    async def debug_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show debug information"""
        user_id = update.effective_user.id
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        debug_msg = f"""
🔍 **Debug Information**

**API Status:**
• Gemini AI: {'✅ Enabled' if self.gemini_coach.enabled else '❌ Disabled'}
• API Key Set: {'✅ Yes' if self.gemini_coach.api_key else '❌ No'}

**User Context:**
• User ID: {user_id}
• Name: {context_data.get('user', {}).first_name if context_data.get('user') else 'Unknown'}
• Streak: {context_data.get('current_streak', 0)} days
• Phase: {context_data.get('execution_phase', 'unknown')}
• Total Activities: {context_data.get('total_activities', 0)}
• Recent Activities: {len(context_data.get('recent_activities', []))}

**Database:**
• User Exists: {'✅ Yes' if context_data.get('user') else '❌ No'}
• Goals: {len(context_data.get('active_goals', []))}

Use /test to test Gemini AI directly.
        """
        
        await update.message.reply_text(debug_msg)
    
    async def market_research_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "📊 **Market Research Command**\n\n"
                "Usage: /research [topic]\n\n"
                "Examples:\n"
                "• /research food delivery apps\n"
                "• /research AI productivity tools\n"
                "• /research local fitness services\n"
                "• /research SaaS for small businesses"
            )
            return
        
        user_id = update.effective_user.id
        user_context = UserContext(self.db, user_id)
        context_data = user_context.get_user_data()
        
        research_topic = ' '.join(context.args)
        
        # Show typing indicator
        await update.message.reply_text(f"📊 Conducting market research on '{research_topic}'... This may take a moment.")
        
        # Conduct research using specialized prompt
        research_response = await self.gemini_coach.conduct_market_research(context_data, research_topic)
        
        # Log this as an activity
        user_context.log_activity(f"Conducted market research on: {research_topic}", "research", context_tags="market_research,analysis")
        
        final_response = f"📊 **Market Research: {research_topic}**\n\n{research_response}\n\n💡 Want business ideas in this space? Try /ideas {research_topic}"
        
        # Split long responses if needed
        if len(final_response) > 4000:
            parts = [final_response[i:i+4000] for i in range(0, len(final_response), 4000)]
            for part in parts:
                await update.message.reply_text(part)
        else:
            await update.message.reply_text(final_response)
    
    async def set_goal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.args:
            goal_text = ' '.join(context.args)
            session = self.db.get_session()
            try:
                goal = Goal(
                    user_id=update.effective_user.id,
                    title=goal_text,
                    goal_type='general'
                )
                session.add(goal)
                session.commit()
                await update.message.reply_text(f"🎯 Goal set: {goal_text}\n\nWhat's the first small step toward this goal?")
            finally:
                session.close()
        else:
            await update.message.reply_text("Usage: /goal Your goal description")
    
    async def weekly_planning(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📋 Set 3 Must-Do Tasks", callback_data="plan_tasks")],
            [InlineKeyboardButton("📈 Review Last Week", callback_data="plan_review")],
            [InlineKeyboardButton("🎯 Set Weekly Goal", callback_data="plan_goal")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📅 **Weekly Planning Session**\n\nLet's set you up for execution success this week:",
            reply_markup=reply_markup
        )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        if query.data == "plan_tasks":
            await query.edit_message_text("📋 List your 3 must-do tasks for this week (one per message):")
        elif query.data == "plan_review":
            await self.show_progress(update, context)
        elif query.data == "plan_goal":
            await query.edit_message_text("🎯 Use /goal to set your weekly goal!")
    
    async def daily_checkin(self):
        """Scheduled daily check-in for all users"""
        session = self.db.get_session()
        try:
            # Only check in with users who've been active in the last 7 days
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = session.query(User).filter(User.last_active > week_ago).all()
            
            for user in active_users:
                try:
                    user_context = UserContext(self.db, user.telegram_id)
                    context_data = user_context.get_user_data()
                    
                    checkin_msg = f"""
🌅 **Daily Check-in Time!** 

Hey {user.first_name}! 

Current streak: **{context_data['current_streak']} days**
Phase: **{context_data['execution_phase'].upper()}**

What's your 5-minute action for today? Even tiny progress counts in the {context_data['execution_phase']} phase!

Reply with what you accomplished or use /stuck if you're feeling blocked. 💪
                    """
                    
                    await self.app.bot.send_message(
                        chat_id=user.telegram_id,
                        text=checkin_msg
                    )
                except Exception as e:
                    print(f"Failed to send daily checkin to user {user.telegram_id}: {e}")
                    
        except Exception as e:
            print(f"Error in daily_checkin: {e}")
        finally:
            session.close()
    
    async def weekly_planning_reminder(self):
        """Scheduled weekly planning reminder"""
        session = self.db.get_session()
        try:
            week_ago = datetime.utcnow() - timedelta(days=7)
            active_users = session.query(User).filter(User.last_active > week_ago).all()
            
            for user in active_users:
                try:
                    await self.app.bot.send_message(
                        chat_id=user.telegram_id,
                        text="📅 **Weekly Planning Time!**\n\nUse /plan to set up your week for execution success! 🚀"
                    )
                except Exception as e:
                    print(f"Failed to send weekly reminder to user {user.telegram_id}: {e}")
        except Exception as e:
            print(f"Error in weekly_planning_reminder: {e}")
        finally:
            session.close()
    
    def run(self):
        """Start the bot and scheduler"""
        self.scheduler.start()
        print("⏰ Scheduler started - daily check-ins and weekly reminders active")
        
        # Start port binding for Render (required for web services)
        self.start_port_binding()
        
        # Start bot polling
        self.app.run_polling()
    
    def start_port_binding(self):
        """Bind to port to satisfy Render web service requirements"""
        import threading
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/health':
                    self.send_response(200)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b'Bot is running')
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                # Suppress HTTP server logs
                pass
        
        def run_server():
            port = int(os.getenv('PORT', 10000))
            server = HTTPServer(('0.0.0.0', port), HealthHandler)
            print(f"🌐 Health server started on port {port}")
            server.serve_forever()
        
        # Run HTTP server in background thread
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

# Main execution
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("🚀 Execution Coach Bot with Gemini AI starting...")
    
    config = RenderConfig()
    config.validate()
    
    print(f"📊 Database URL configured: {config.DATABASE_URL[:30]}...")
    
    # Debug environment variables
    print(f"🔑 TELEGRAM_TOKEN: {'✅ Set' if config.TELEGRAM_TOKEN else '❌ Missing'}")
    print(f"🤖 GEMINI_API_KEY: {'✅ Set' if config.GEMINI_API_KEY else '❌ Missing'}")
    if config.GEMINI_API_KEY:
        print(f"🔑 Gemini key length: {len(config.GEMINI_API_KEY)} chars")
        print(f"🔑 Gemini key starts: {config.GEMINI_API_KEY[:10]}...")
    
    try:
        bot = ExecutionCoachBot(
            config.TELEGRAM_TOKEN, 
            config.DATABASE_URL, 
            config.GEMINI_API_KEY
        )
        
        print("🤖 Bot initialized successfully")
        print("📊 Database tables created")
        print("⏰ Scheduler activated")
        print("🌐 Starting polling...")
        
        bot.run()
        
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)