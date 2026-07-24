# This is a Python news_agent script. Used for just that, as a personal news outlet curated for the
# topics the individual picks. Using keywords and RSS feeds the agent sends summary's of key importance
# to a dedicated Wahtsapp number.
#
import feedparser
import pywhatkit

# RSS feeds
RSS_Feeds = {
    'BBC News': 'https://feeds.bbci.co.uk/news/rss.xml',
    'The Verge': 'https://www.theverge.com/rss/index.xml',
    # Add more feeds here...
}

# WhatsApp message recipient
recipient_number = "+1234567890"  # Replace with your number

# Keywords for filtering
keywords = ["ie..."'tech', 'sports', 'world news']

def send_whatsapp_message(message):
    pywhatkit.sendwhatmsg_instantly(recipient_number, message, 15, True, 5)  # Wait 15 seconds before sending
    print("Message sent!")

def get_articles():
    articles = []
    for source, feed in RSS_Feeds.items():
        parsed_feed = feedparser.parse(feed)
        entries = [(source, entry) for entry in parsed_feed.entries]
        articles.extend(entries)
    return articles

def summarize_article(article):
    from sumy.parsers.plaintext import PlaintextParser
    from sumy.summarizers.lex_rank import LexRankSummarizer

    parser = PlaintextParser.from_string(article[1].summary, tokenizer=None)
    summarizer = LexRankSummarizer()
    summary = summarizer(parser.document, 1)[0].value

    return summary

def filter_by_keywords(article):
    for keyword in keywords:
        if keyword.lower() in article[1].title.lower():
            return True
    return False

def main():
    articles = get_articles()
    for article in articles:
        if filter_by_keywords(article):
            summary = summarize_article(article)
            send_whatsapp_message(summary)

if _name_ == "_main_":
    main()
