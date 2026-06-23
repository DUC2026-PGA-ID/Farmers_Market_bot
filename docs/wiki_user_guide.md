# 🌾 Farmers Market Bot - User Guide

Welcome to the **Farmers Market Bot**! This bot connects Cambodian farmers with buyers by providing real-time commodity prices, a catalog of crops, and a retail marketplace. 

Below is a step-by-step guide on how to use the bot.

---

## 1. Getting Started
To begin using the bot, search for the bot in Telegram and click **Start**, or type:
`/start`

The bot will ask you to register:
1. **Name**: Enter your full name in Khmer or English.
2. **Phone Number**: Enter your phone number (e.g., 012345678). If you enter text instead of numbers, the bot will kindly reject it and ask you to enter a valid number.

Once registered, you will have access to all the bot's features!

---

## 2. Viewing the Catalog
To see all the crops supported by our platform, type:
`/view_catalog`

- The bot will display a list of buttons containing crop names (e.g., ពោត, អង្ករ, ស្វាយ).
- **Click on any crop button** to see detailed information, including its description, quality standards, and measurement unit.

---

## 3. Checking Market Prices
To view the daily updated market prices in Phnom Penh, type:
`/price`

- The bot will reply with a list of crops and their current price per kg/sack.
- You will see trend indicators (📈 or 📉) showing if the price has increased or decreased compared to yesterday.
- *(Note: Prices are fetched in the background and cached for fast responses!)*

---

## 4. Selling Your Crops
If you are a farmer and want to post an item for sale, use the `/sell` command.

**Format:**
`/sell [Crop Name], [Grade], [Quantity], [Price]`

**Example:**
`/sell ស្រូវសើម, ប្រភេទ A, ៥០០គីឡូ, ១២០០៛/គីឡូ`

Your listing will instantly be added to the marketplace.

---

## 5. Buying / Viewing the Marketplace
If you are a buyer looking for crops, type:
`/market`

- The bot will display the latest 10 listings posted by farmers.
- You will see the Crop Name, Quantity, Price, and the Seller's contact info (Phone & Telegram Username).

---

## 6. Weather Forecast
To check the weather forecast for your farm, type:
`/weather`

- The bot will display a button asking for your location.
- **Click "ផ្ញើទីតាំងរបស់ខ្ញុំ" (Send My Location)**.
- The bot will instantly reply with the 7-day weather forecast (Rainfall & Temperature) for your specific area.

---

## 7. Additional Commands
- `/location` - Allows you to update your farm's GPS location manually.
- `/buyers` - Views the list of verified buyers in the network.
