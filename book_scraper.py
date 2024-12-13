import os
import json
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin

class BookScraper:
    def __init__(self):
        self.session = None
        self.base_url = "https://basecamp.com"

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def get_chapter_links(self, url: str) -> List[str]:
        """Get all chapter links from the table of contents"""
        async with self.session.get(url) as response:
            if response.status != 200:
                print(f"Error: Failed to fetch table of contents. Status: {response.status}")
                return []

            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            links = []

            # Find all chapter links
            for link in soup.find_all('a'):
                href = link.get('href', '')
                if 'gettingreal' in href and href != '/gettingreal':
                    full_url = urljoin(self.base_url, href)
                    links.append(full_url)

            return sorted(list(set(links)))  # Remove duplicates and sort

    async def scrape_chapter(self, url: str) -> Dict:
        """Scrape a single chapter's content"""
        print(f"\nDEBUG: Scraping {url}")
        async with self.session.get(url) as response:
            if response.status != 200:
                print(f"Error: Failed to fetch chapter {url}. Status: {response.status}")
                return {}

            html = await response.text()
            soup = BeautifulSoup(html, 'html.parser')
            print(f"DEBUG: HTML length: {len(html)}")

            # Remove navigation elements
            for nav in soup.find_all(['nav', 'footer', 'style', 'script']):
                nav.decompose()

            content = {
                'url': url,
                'title': '',
                'content': [],
                'sections': [],
                'code_blocks': []
            }

            # Extract title and section
            main_content = soup.find('main', id='main')
            if main_content:
                print("DEBUG: Found main content")
                # Find the first heading as title
                title = main_content.find(['h1', 'h2', 'h3'])
                if title:
                    content['title'] = title.get_text(strip=True)
                    print(f"DEBUG: Found title: {content['title']}")
                    # Remove the title from main_content to avoid duplication
                    title.decompose()

                # Extract content
                for element in main_content.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol']):
                    if element.name.startswith('h'):
                        section_text = element.get_text(strip=True)
                        if section_text:
                            print(f"DEBUG: Found heading: {section_text}")
                            content['sections'].append({
                                'level': int(element.name[1]),
                                'text': section_text
                            })
                    elif element.name == 'p':
                        text = element.get_text(strip=True)
                        if text and not any(skip in text.lower() for skip in [
                            'next:', 'previous:', 'copyright', 'browser', 'firefox', 'chrome'
                        ]):
                            print(f"DEBUG: Found paragraph: {text[:50]}...")
                            content['content'].append(text)
                    elif element.name == 'pre':
                        code = element.get_text(strip=True)
                        if code:
                            print(f"DEBUG: Found code block: {len(code)} chars")
                            content['code_blocks'].append(code)
                    elif element.name in ['ul', 'ol']:
                        list_items = [li.get_text(strip=True) for li in element.find_all('li')]
                        if list_items:
                            print(f"DEBUG: Found list with {len(list_items)} items")
                            content['content'].append({
                                'type': element.name,
                                'items': list_items
                            })
            else:
                print("DEBUG: No article found!")

            return content

    async def scrape_book(self, start_url: str) -> List[Dict]:
        """Scrape the entire book"""
        print("Getting chapter links...")
        chapter_links = await self.get_chapter_links(start_url)
        print(f"Found {len(chapter_links)} chapters")

        chapters = []
        for i, link in enumerate(chapter_links, 1):
            print(f"Scraping chapter {i}/{len(chapter_links)}: {link}")
            chapter = await self.scrape_chapter(link)
            if chapter:
                chapters.append(chapter)
            await asyncio.sleep(0.5)  # Be nice to the server

        return chapters

    def convert_to_markdown(self, chapters: List[Dict]) -> str:
        """Convert chapters to markdown format"""
        print("\nDEBUG: Starting markdown conversion")
        print(f"DEBUG: Processing {len(chapters)} chapters")

        markdown = []

        # Book title and introduction
        markdown.extend([
            "# Getting Real\n",
            "by Basecamp\n\n"
        ])

        # Add book introduction
        intro = next((ch for ch in chapters if "What is Getting Real" in ch.get('title', '')), None)
        if intro:
            print("DEBUG: Found introduction")
            for content in intro.get('content', []):
                if isinstance(content, str):
                    markdown.append(f"{content}\n\n")
                elif isinstance(content, dict) and 'items' in content:
                    markdown.append("\n")
                    for item in content['items']:
                        markdown.append(f"* {item}\n")
                    markdown.append("\n")

        markdown.append("---\n\n")

        # Generate Table of Contents with proper section links
        markdown.append("# Table of Contents\n\n")
        print("DEBUG: Generating table of contents")

        current_section = None
        for chapter in chapters:
            title = chapter.get('title', '').strip()
            if not title or any(skip in title.lower() for skip in [
                'next:', 'previous:', 'heads up', 'copyright', 'back to',
                'basecamp.com', 'the smarter'
            ]):
                continue

            # Extract section and chapter title
            parts = title.split(' - ')
            if len(parts) > 1:
                section = parts[1].strip()
                chapter_title = parts[0].strip()
            else:
                section = None
                chapter_title = title

            # Create section anchor
            if section and section != current_section:
                section_anchor = section.lower().replace(' ', '-')
                markdown.append(f"\n## {section}\n\n")
                current_section = section
                print(f"DEBUG: Added section: {section}")

            # Create chapter anchor and link
            chapter_anchor = chapter_title.lower().replace(' ', '-')
            markdown.append(f"* [{chapter_title}](#{chapter_anchor})\n")
            print(f"DEBUG: Added TOC entry: {chapter_title}")

        markdown.append("\n---\n\n")

        # Chapter Content
        print("\nDEBUG: Adding chapter content")
        for chapter in chapters:
            title = chapter.get('title', '').strip()
            if not title or any(skip in title.lower() for skip in [
                'next:', 'previous:', 'heads up', 'copyright', 'back to',
                'basecamp.com', 'the smarter'
            ]):
                continue

            print(f"\nDEBUG: Processing chapter: {title}")
            # Add chapter title
            chapter_anchor = title.lower().replace(' ', '-')
            markdown.append(f"# {title}\n\n")

            # Add sections with proper hierarchy
            for section in chapter.get('sections', []):
                if isinstance(section, dict) and 'text' in section:
                    level = min(section.get('level', 2), 6)
                    section_text = section['text'].strip()
                    if section_text:
                        markdown.append(f"{'#' * level} {section_text}\n\n")
                        print(f"DEBUG: Added section heading: {section_text}")

            # Add content with proper formatting
            content_count = 0
            for item in chapter.get('content', []):
                if isinstance(item, dict) and 'type' in item and 'items' in item:
                    # Handle lists
                    markdown.append("\n")
                    for i, li in enumerate(item['items'], 1):
                        if item['type'] == 'ul':
                            markdown.append(f"* {li}\n")
                        else:  # ol
                            markdown.append(f"{i}. {li}\n")
                    markdown.append("\n")
                    content_count += 1
                elif isinstance(item, str) and item.strip():
                    # Handle paragraphs, skip empty ones
                    markdown.append(f"{item}\n\n")
                    content_count += 1
            print(f"DEBUG: Added {content_count} content items")

            # Add code blocks
            for code in chapter.get('code_blocks', []):
                if code.strip():
                    markdown.append(f"```\n{code}\n```\n\n")
                    print("DEBUG: Added code block")

            markdown.append("---\n\n")

        print("DEBUG: Markdown conversion complete")
        return "".join(markdown)

    async def save_markdown(self, markdown: str, output_file: str = "book.md"):
        """Save the markdown content to a file"""
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Book has been saved to {output_file}")

async def main():
    async with BookScraper() as scraper:
        print("Starting book scraping...")
        chapters = await scraper.scrape_book("https://basecamp.com/gettingreal")
        print("Converting to markdown...")
        markdown = scraper.convert_to_markdown(chapters)
        print("Saving to file...")
        await scraper.save_markdown(markdown)
        print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
