# AI Execution Coach Bot

An intelligent Telegram bot powered by Gemini AI that helps solo entrepreneurs overcome procrastination, build momentum, and execute on their business ideas through personalized coaching and specialized AI agents.

## 🤖 Features

### 3 Specialized AI Agents

**🎯 Execution Coach** (Default Mode)
- Daily accountability and check-ins
- Procrastination breakthrough strategies  
- Goal tracking and momentum building
- Personalized coaching based on your patterns
- 5-minute action suggestions

**💡 Business Ideas Generator**
- Creative, viable business concepts
- Implementation roadmaps and resource estimates
- Ideas tailored to solo entrepreneurs
- Market opportunity analysis

**📊 Market Research Agent**
- Competitive landscape analysis
- Market sizing and trends
- Customer segment insights
- Strategic recommendations

### Key Capabilities
- ✅ **Memory & Context**: Remembers your conversations, goals, and patterns
- ✅ **Personal Tracking**: Maintains streaks, activities, and progress
- ✅ **Phase-Aware Coaching**: Adapts advice to your execution phase
- ✅ **Resource-Conscious**: Advice tailored for bootstrap entrepreneurs
- ✅ **Automated Check-ins**: Daily motivation and weekly planning

## 🚀 Quick Start

### 1. Get API Keys
- **Telegram Bot**: Message [@BotFather](https://t.me/botfather) to create your bot
- **Gemini AI**: Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)

### 2. Deploy to Render (Recommended)
1. Fork this repository
2. Connect to [Render](https://render.com)
3. Deploy using the included `render.yaml`
4. Add environment variables in Render dashboard:
   - `TELEGRAM_TOKEN`: Your bot token
   - `GEMINI_API_KEY`: Your Gemini API key

### 3. Local Development
```bash
# Clone repository
git clone <your-repo-url>
cd execution-coach-bot

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# Run locally
python bot.py
```

## 📱 Commands

### Setup Commands
- `/start` - Initialize your profile and see welcome message
- `/idea [description]` - Set your current business idea
- `/phase [planning|validation|mvp|traction]` - Set execution phase
- `/goal [description]` - Set a goal with deadline

### Daily Commands
- `/stuck` - Get immediate help when procrastinating
- `/win [description]` - Log any victory to build momentum
- `/progress` - View your streaks and activity patterns
- `/plan` - Start weekly planning session

### AI Agent Commands
- `/ideas [theme]` - Generate creative business ideas
- `/research [topic]` - Conduct comprehensive market research
- `/modes` - See all available agent modes

### Examples
```
/ideas AI productivity tools
/research food delivery market
/goal Launch MVP in 30 days
/win Made my first customer call!
/stuck I keep avoiding sales outreach
```

## 🧠 How It Works

### Personalized Context
The bot maintains comprehensive context about you:
- Your business idea and execution phase
- Daily activity streaks and patterns
- Goals and progress tracking
- Previous conversations and responses
- What motivates you vs. what blocks you

### AI-Powered Responses
Using Gemini AI, the bot provides:
- **Contextual Coaching**: References your specific history and patterns
- **Phase-Specific Advice**: Different guidance for planning vs. validation vs. MVP phases
- **Resource-Aware Suggestions**: Recommendations for solo entrepreneurs with limited budgets
- **Pattern Recognition**: Learns what works for your specific situation

### Example Conversation Flow
```
User: I have an idea for an AI task manager but don't know if there's a market

Bot: [Uses Business Ideas Agent] 
Let me help you explore this! AI task management is hot right now...

User: /research AI task management tools

Bot: [Uses Market Research Agent]
Here's what I found about the AI task management market...

User: This looks promising but I'm overwhelmed and don't know where to start

Bot: [Uses Execution Coach with your context]
I see you're in the validation phase with a 3-day streak. Based on your pattern, 
you break through overwhelm by starting with one tiny action. Here's your 
5-minute task: find and message one person who struggles with task management...
```

## 🗄️ Database Schema

The bot uses PostgreSQL to maintain memory:
- **Users**: Profile, business idea, execution phase, streaks
- **Goals**: Objectives with deadlines and status
- **Activities**: Every action logged with context and mood
- **Progress**: Quantitative metrics over time  
- **Conversations**: Full chat history with context tags

## 🔧 Technical Details

### Built With
- **Python 3.11+**
- **python-telegram-bot** - Telegram Bot API
- **SQLAlchemy** - Database ORM
- **Google Generative AI** - Gemini AI integration
- **APScheduler** - Automated check-ins
- **PostgreSQL** - Data persistence

### Architecture
- **Modular Design**: Separate classes for database, AI coaching, and bot logic
- **Context Management**: Smart context loading based on user patterns
- **Graceful Fallbacks**: Works without Gemini API (reduced functionality)
- **Scalable**: Supports multiple users with isolated data

### Deployment
- **Render** (Recommended): Free tier with PostgreSQL
- **Railway**: $5/month with automatic scaling
- **Local/VPS**: Self-hosted with Docker support

## 📊 Costs

### Free Tier Options
- **Render**: Free with 500MB PostgreSQL, sleeps after 15min inactivity
- **Gemini AI**: Generous free tier for personal use
- **Telegram Bot**: Completely free

### Paid Recommendations
- **Render Pro**: $7/month for always-on service
- **Total Cost**: ~$7/month for production-ready coaching bot

## 🛠️ Customization

### Adding New Commands
```python
# In ExecutionCoachBot class
self.app.add_handler(CommandHandler("custom", self.custom_command))

async def custom_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Your custom logic here
    pass
```

### Modifying AI Prompts
Edit the prompts in `GeminiCoach.load_specialized_prompts()` method to customize coaching style and focus areas.

### Adding New Agent Types
Create new methods in `GeminiCoach` following the pattern of `generate_business_ideas()` and `conduct_market_research()`.

## 🔒 Privacy & Security

- **Local Data**: All personal data stored in your own database
- **API Keys**: Securely managed through environment variables  
- **No Third-Party Sharing**: Data never leaves your deployment
- **User Isolation**: Each user's data is completely separate

## 🐛 Troubleshooting

### Common Issues

**Bot Not Responding**
- Check `TELEGRAM_TOKEN` in environment variables
- Verify bot is running (check logs)
- Ensure webhook is not set (use polling mode)

**Database Errors**
- Verify `DATABASE_URL` format: `postgresql://user:pass@host:port/db`
- Check database is running and accessible
- Ensure tables are created (bot creates them automatically)

**Gemini AI Not Working**
- Verify `GEMINI_API_KEY` is set correctly
- Check API quota and usage limits
- Bot falls back to basic responses if Gemini unavailable

### Logs Location
- **Render**: View in service dashboard logs tab
- **Local**: Printed to console
- **Production**: Check your deployment platform's logging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

MIT License - Feel free to use for personal or commercial projects.

## 📞 Support

Having issues? 
1. Check the troubleshooting section above
2. Review environment variable setup
3. Check deployment platform logs
4. Open an issue with detailed error information

---

**Built for solo entrepreneurs who struggle with execution.** 
*Because ideas are worthless without action.* 🚀