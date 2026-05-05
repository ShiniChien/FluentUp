"""
core/question_bank.py
-------------------------
Pre-built Part 1 opening question bank — 50 everyday domains, 2-3 questions each.
Used instead of an LLM call for the first question to improve speed and reliability.
"""
from __future__ import annotations
import random

# Domain → list[question]
PART1_QUESTION_BANK: dict[str, list[str]] = {
    "hometown": [
        "Where are you from originally?",
        "What do you like most about the place you grew up in?",
        "Has your hometown changed much over the years?",
    ],
    "accommodation": [
        "Do you live in a house or an apartment?",
        "What is your favourite room in your home, and why?",
        "Would you prefer to live in the city or the countryside?",
    ],
    "work_or_study": [
        "Do you work or are you a student at the moment?",
        "What made you choose your current job or field of study?",
        "Do you enjoy what you do for work or study?",
    ],
    "daily_routine": [
        "What does a typical day look like for you?",
        "Are you more productive in the morning or in the evening?",
        "Has your daily routine changed recently?",
    ],
    "food_and_cooking": [
        "Do you enjoy cooking?",
        "What kind of food do you eat most often?",
        "Do you prefer eating at home or eating out at restaurants?",
    ],
    "coffee_and_tea": [
        "Do you prefer coffee or tea?",
        "How often do you drink coffee or tea throughout the day?",
        "Do you have a favourite café or place to grab a drink?",
    ],
    "music": [
        "What kind of music do you enjoy listening to?",
        "Do you play any musical instruments?",
        "When do you usually listen to music?",
    ],
    "movies_and_tv": [
        "Do you enjoy watching films?",
        "What kinds of TV shows do you watch in your free time?",
        "Do you prefer watching movies at the cinema or at home?",
    ],
    "reading": [
        "Do you enjoy reading books?",
        "What type of books or articles do you like to read?",
        "Did you read a lot when you were a child?",
    ],
    "sports": [
        "Do you enjoy playing any sports?",
        "Is there a sport you follow or watch regularly?",
        "Did you play sports when you were younger?",
    ],
    "hobbies": [
        "What do you like to do in your free time?",
        "Have you picked up any new hobbies recently?",
        "Is there a hobby you have always wanted to try?",
    ],
    "travel": [
        "Do you enjoy travelling?",
        "What is the most interesting place you have ever visited?",
        "Do you prefer travelling alone or with other people?",
    ],
    "technology": [
        "How much time do you spend on your phone each day?",
        "Do you think technology has made your life easier or more complicated?",
        "What apps or tools do you use most often?",
    ],
    "social_media": [
        "Do you use social media very often?",
        "Which social media platform do you use the most?",
        "Do you think social media has a positive or negative impact on people?",
    ],
    "weather_and_seasons": [
        "What is the weather like where you live?",
        "Do you have a favourite season?",
        "How does the weather affect your mood or daily plans?",
    ],
    "shopping": [
        "Do you enjoy going shopping?",
        "Do you prefer shopping online or in person?",
        "How often do you go shopping for clothes?",
    ],
    "fashion_and_clothes": [
        "Do you pay much attention to fashion?",
        "Do you have a particular style when it comes to clothing?",
        "Has your sense of style changed over the years?",
    ],
    "health_and_exercise": [
        "Do you try to keep fit?",
        "What do you do to stay healthy?",
        "How important do you think exercise is in daily life?",
    ],
    "sleep": [
        "How many hours of sleep do you usually get?",
        "Are you the kind of person who stays up late or goes to bed early?",
        "Do you think most people get enough sleep these days?",
    ],
    "nature_and_outdoors": [
        "Do you enjoy spending time outdoors?",
        "How often do you go to parks or natural areas?",
        "What is your favourite outdoor activity?",
    ],
    "pets_and_animals": [
        "Do you have any pets?",
        "Did you have pets when you were growing up?",
        "Are you generally fond of animals?",
    ],
    "photography": [
        "Do you enjoy taking photographs?",
        "What do you usually take photos of?",
        "Do you prefer taking photos with your phone or a camera?",
    ],
    "art_and_painting": [
        "Are you interested in art?",
        "Have you ever tried painting or drawing?",
        "What kind of art do you find most appealing?",
    ],
    "languages": [
        "How long have you been learning English?",
        "Do you speak any other languages besides English?",
        "What do you find most challenging about learning a language?",
    ],
    "games_and_gaming": [
        "Do you enjoy playing video games?",
        "Did you play board games or video games when you were a child?",
        "How often do you play games in your free time?",
    ],
    "dancing": [
        "Do you enjoy dancing?",
        "Have you ever taken dance lessons?",
        "Is dancing popular in your culture?",
    ],
    "singing_and_karaoke": [
        "Do you enjoy singing?",
        "Have you ever done karaoke?",
        "Do you sing when you are at home or in the shower?",
    ],
    "cooking_skills": [
        "Are you a good cook?",
        "Who does most of the cooking in your household?",
        "Is there a dish you especially enjoy making?",
    ],
    "family": [
        "Do you have a large or small family?",
        "How much time do you spend with your family each week?",
        "Are you close to your family members?",
    ],
    "friends": [
        "Would you say you have a large group of friends or just a few close ones?",
        "How do you usually keep in touch with your friends?",
        "Do you find it easy to make new friends?",
    ],
    "neighbours_and_community": [
        "Do you know your neighbours well?",
        "Is there a strong sense of community where you live?",
        "How important do you think it is to have good neighbours?",
    ],
    "public_transport": [
        "What is the main way you get around your city?",
        "Do you use public transport often?",
        "Do you think public transport in your area is reliable?",
    ],
    "cycling": [
        "Do you ride a bike?",
        "Is cycling popular in your city?",
        "Would you prefer to cycle rather than drive?",
    ],
    "restaurants_and_cafes": [
        "How often do you eat out at restaurants?",
        "Do you have a favourite type of restaurant?",
        "What do you look for when choosing a restaurant?",
    ],
    "holidays_and_festivals": [
        "What is your favourite holiday or festival of the year?",
        "How do you usually celebrate national holidays?",
        "Are festivals an important part of the culture where you are from?",
    ],
    "birthday_celebrations": [
        "How do you usually celebrate your birthday?",
        "Do you prefer big birthday parties or small gatherings?",
        "Is celebrating birthdays important to you?",
    ],
    "gifts_and_giving": [
        "Do you enjoy giving gifts to people?",
        "Is it easy for you to choose gifts for others?",
        "What is the best gift you have ever received?",
    ],
    "plants_and_gardening": [
        "Do you have any plants at home?",
        "Do you enjoy gardening?",
        "Is gardening a popular hobby among people you know?",
    ],
    "environment_and_recycling": [
        "Do you try to be environmentally friendly in your daily life?",
        "Does your city have good recycling facilities?",
        "What do you think individuals can do to help the environment?",
    ],
    "volunteering_and_charity": [
        "Have you ever done any volunteer work?",
        "Do you think it is important for people to give to charity?",
        "What causes or issues do you care most about?",
    ],
    "online_learning": [
        "Have you ever taken an online course?",
        "Do you prefer learning online or in a classroom?",
        "What is something you have recently learned online?",
    ],
    "time_management": [
        "Would you say you are good at managing your time?",
        "Do you use any particular methods or tools to stay organised?",
        "Do you find it difficult to balance work or study with personal life?",
    ],
    "punctuality": [
        "Are you usually on time for appointments and meetings?",
        "How do you feel when other people are late?",
        "Is punctuality considered important in your culture?",
    ],
    "concentration_and_focus": [
        "Do you find it easy to concentrate on tasks for a long time?",
        "What do you do when you need to focus on something important?",
        "Do you prefer working in silence or with background noise?",
    ],
    "memory": [
        "Would you say you have a good memory?",
        "What kinds of things do you tend to forget most easily?",
        "Do you use any tricks or techniques to help you remember things?",
    ],
    "dreams": [
        "Do you often remember your dreams when you wake up?",
        "Have you ever had a dream that felt very real?",
        "Do you think dreams have any meaning?",
    ],
    "colours": [
        "Do you have a favourite colour?",
        "Do you think colours can influence a person's mood?",
        "Have your favourite colours changed since you were a child?",
    ],
    "museums_and_galleries": [
        "Do you enjoy visiting museums?",
        "When did you last go to a museum or art gallery?",
        "Do you think museums are an important part of a city?",
    ],
    "libraries": [
        "Do you visit libraries often?",
        "Did you use the library a lot when you were a student?",
        "Do you think libraries are still relevant in the digital age?",
    ],
    "numbers_and_math": [
        "Are you good with numbers?",
        "Did you enjoy mathematics at school?",
        "Do you use maths much in your daily life?",
    ],
    "future_plans": [
        "Do you have any big plans for the coming year?",
        "Where do you see yourself in five years' time?",
        "Is there something you really hope to achieve in the future?",
    ],
}


def pick_opening_question(profile_occupation: str = "") -> tuple[str, str]:
    """
    Return (domain, question) randomly from the bank.
    If profile_occupation is 'student', slightly favour study-adjacent domains;
    if 'worker', slightly favour work-adjacent domains.
    """
    domains = list(PART1_QUESTION_BANK.keys())

    # Soft bias based on profile — boost relevant domains without excluding others
    weights = [1] * len(domains)
    for i, d in enumerate(domains):
        if profile_occupation == "student" and d in ("online_learning", "languages", "libraries", "future_plans"):
            weights[i] = 3
        elif profile_occupation == "worker" and d in ("work_or_study", "time_management", "daily_routine", "future_plans"):
            weights[i] = 3

    domain = random.choices(domains, weights=weights, k=1)[0]
    question = random.choice(PART1_QUESTION_BANK[domain])
    return domain, question


def all_questions_flat() -> list[str]:
    """Return all questions as a flat list (useful for batch generation)."""
    return [q for qs in PART1_QUESTION_BANK.values() for q in qs]
