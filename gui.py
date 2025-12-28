import json
import platform
import subprocess
import time
from pathlib import Path

import streamlit as st
from pinterest_dl import PinterestDL

# ========================== Configuration Section ==========================
VERSION = "0.2.5"
MODE_OPTIONS = {
    "Board": ":material/web: Board",
    "Search": ":material/search: Search",
}
COOKIES_PATH = Path("cookies/cookies.json")
COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)


# ========================== Util Section ==========================
def open_directory(path):
    if platform.system() == "Windows":
        path = str(path)
        subprocess.Popen(["explorer", path])
    elif platform.system() == "Darwin":  # macOS
        subprocess.Popen(["open", path])
    elif platform.system() == "Linux":  # Linux
        subprocess.Popen(["xdg-open", path])
    else:
        raise OSError("Unsupported operating system")


def check_ffmpeg() -> bool:
    """Check if ffmpeg is installed and accessible."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


# ========================== Internal global variables ==========================
IS_FFMEPEG_EXIST = check_ffmpeg()


# ========================== UI Functions Section ==========================
def init_state():
    """Initialize Streamlit session state variables."""
    if "use_cookies" not in st.session_state:
        st.session_state.use_cookies = False
    if "ensure_cap" not in st.session_state:
        st.session_state.ensure_cap = False


def setup_ui():
    """Set up main UI components and return user inputs."""
    st.title(f"Pinterest DL {VERSION}")
    mode = st.segmented_control(
        "Mode",
        list(MODE_OPTIONS.values()),
        selection_mode="single",
        default=MODE_OPTIONS["Board"],
    )

    # Query input depends on selected mode.
    if mode == MODE_OPTIONS["Board"]:
        query = st.text_input(
            "Pinterest URL", placeholder="https://www.pinterest.com/pin/1234567890/ or visual search URL"
        )
    else:
        query = st.text_input("Search Query", placeholder="Impressionist Art")

    # Gather project information.
    project_name, image_limit, recurse_factor = project_section()
    with st.expander("Scrape Options"):
        res_x, res_y = quality_section()
        timeout, delay = scraping_section()
        caption_type = caption_selection()
        download_videos = video_section()
        use_browser, driver, headless, incognito = browser_section()
        cookies_section()

    return (
        query,
        project_name,
        res_x,
        res_y,
        image_limit,        recurse_factor,        timeout,
        delay,
        mode,
        caption_type,
        download_videos,
        use_browser,
        driver,
        headless,
        incognito,
    )


def video_section():
    """UI for video download option."""
    if not IS_FFMEPEG_EXIST:
        download_videos = st.toggle(
            "Download Videos",
            value=False,
            disabled=True,
            help="Download Videos if ffmpeg is installed and added to PATH. (`Not Detected`)",
        )
    else:
        download_videos = st.toggle(
            "Download Videos",
            value=False,
            help="Download Videos if available.",
        )
    return download_videos


def cookies_section():
    """UI for cookie usage toggle and button for login dialog."""
    col1, col2 = st.columns(2)
    with col1:
        use_cookies = st.toggle("Use Cookies", value=st.session_state.use_cookies)
    with col2:
        if use_cookies:
            st.session_state.use_cookies = True
            if st.button("Get Cookies"):
                login_dialog()
        else:
            st.session_state.use_cookies = False

    if use_cookies and not COOKIES_PATH.exists():
        st.warning(f"No cookies found under path `./{COOKIES_PATH.as_posix()}`!")


def caption_selection():
    """UI for selecting caption options."""
    caption_type = st.selectbox(
        "Caption Type",
        ["none", "txt", "json", "metadata"],
        index=0,
    )
    ensure_cap = st.toggle(
        "Ensure Caption",
        value=False,
        help="Ensure each image has a caption. (Set `Caption Type` other than `none` to enable)",
        disabled=(caption_type == "none"),
    )
    st.session_state.ensure_cap = ensure_cap
    return caption_type


def browser_section():
    """UI for browser scraping options."""
    use_browser = st.toggle("Use Browser Scraping", value=False, help="Use browser instead of API for scraping (slower but may work for some URLs)")
    driver = None
    headless = True
    incognito = True
    if use_browser:
        driver = st.selectbox("Webdriver", ["chrome", "firefox"])
        options = st.pills(
            "Driver Options", ["Headless", "Incognito"], selection_mode="multi", default=["Headless", "Incognito"]
        )
        headless = "Headless" in options
        incognito = "Incognito" in options
    return use_browser, driver, headless, incognito


@st.dialog("Pinterest Login")
def login_dialog():
    """Dialog box for logging in and retrieving cookies."""
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    col1, col2 = st.columns(2)
    with col1:
        driver = st.selectbox("Webdriver", ["chrome", "firefox"])
    with col2:
        after_sec = st.number_input("Seconds to wait after login", 0, 60, 7, step=1)

    options = st.pills(
        "Driver Options", ["Headless", "Incognito"], selection_mode="multi", default=["Headless"]
    )
    headless = "Headless" in options
    incognito = "Incognito" in options

    if st.button("Login"):
        if not email or not password:
            st.warning("Please enter email and password!")
        else:
            with st.spinner("Logging in... (this might take a while)"):
                download_cookies(email, password, after_sec, headless, incognito, driver)
                st.rerun()


def project_section():
    """UI for specifying the project name and image limit."""
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        project_name = st.text_input("Project Name", placeholder="Concept Art")
    with col2:
        image_limit = st.number_input("Image Limit", 1, 100000, 100, step=1)
    with col3:
        recurse_factor = st.number_input("Recurse Factor", 0, 1000, 1, step=1, help="Number of recursive visual search levels (0 = no recursion, 1 = one level)")
    return project_name, image_limit, recurse_factor


def quality_section():
    """UI for choosing minimum image resolution."""
    col1, col2 = st.columns(2)
    with col1:
        res_x = st.number_input("Min Resolution X", 0, 4096, 0, step=64)
    with col2:
        res_y = st.number_input("Min Resolution Y", 0, 4096, 0, step=64)
    return res_x, res_y


def scraping_section() -> tuple[float, float]:
    """UI for setting timeout and delay options."""
    timeout = st.slider("Timeout (sec)", 0.0, 1000.0, 120.0, help="Timeout for each request (increase for large limits)")
    delay = st.slider("Delay (sec)", 0.0, 2.0, 0.8, help="Delay between requests")
    return timeout, delay


def footer():
    """Custom footer displayed on the page."""
    bg_color = "#262730"
    txt_color = "#FFF"
    border_color = "#444"
    custom_css = f"""
    <style>
        footer {{ visibility: hidden; }}
        .stApp {{ margin-bottom: 60px; }}
        .custom-footer {{
            position: fixed;
            left: 0;
            bottom: 0;
            width: 100%;
            background-color: {bg_color};
            color: {txt_color};
            text-align: center;
            padding: 10px;
            font-size: 12px;
            border-top: 1px solid {border_color};
            z-index: 100;
        }}
        .custom-footer a {{
            color: {txt_color};
            text-decoration: none;
        }}
        .custom-footer a:hover {{
            text-decoration: underline;
        }}
    </style>
    """
    custom_footer = """
    <div class="custom-footer">
        Made with ❤️ by <a href="https://github.com/Sean1832/pinterest-dl-gui" target="_blank">Sean1832</a>
        | <a href="https://www.buymeacoffee.com/zekezhang" target="_blank">Buy me a coffee</a>
    </div>
    """
    st.markdown(custom_css + custom_footer, unsafe_allow_html=True)


# ========================== Scraper Functions Section ==========================
def download_cookies(email, password, after_sec, headless, incognito, driver):
    """Perform login and save cookies."""
    cookies = (
        PinterestDL.with_browser(driver, headless=headless, incognito=incognito, timeout=10)
        .login(email, password)
        .get_cookies(after_sec=after_sec)
    )
    with open(COOKIES_PATH, "w") as f:
        json.dump(cookies, f)


def scrape_images(
    url,
    project_name,
    project_dir,
    res_x,
    res_y,
    limit,
    recurse_factor,
    timeout,
    delay,
    caption,
    download_videos,
    use_browser,
    driver,
    headless,
    incognito,
):
    """Scrape images from a Pinterest board URL."""
    from pinterest_dl.utils import io
    session_time = time.strftime("%Y%m%d%H%M%S")
    cache_path = Path("downloads", "_cache")
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_filename = Path(cache_path, f"{project_name}_{session_time}.json")

    if not url or not project_name:
        st.session_state['error'] = "Please enter a URL and Project Name!"
        return

    if project_dir.exists():
        st.session_state['warning'] = "Project already exists! Merge with existing data."

    # Extract original pin ID if URL is a pin URL
    original_pin_id = None
    if '/pin/' in url:
        import re
        match = re.search(r'/pin/(\d+)/', url)
        if match:
            original_pin_id = match.group(1)

    if use_browser:
        # Patch to continue on download errors
        from pinterest_dl.low_level.http.downloader import PinterestMediaDownloader as Downloader
        original_download_concurrent = Downloader.download_concurrent
        def patched_download_concurrent(self, media_list, output_dir, download_streams=False, num_threads=4, fail_fast=True):
            return original_download_concurrent(self, media_list, output_dir, download_streams, num_threads, fail_fast=False)
        Downloader.download_concurrent = patched_download_concurrent

        # Patch to increase timeout for scraping and add load more clicking
        from pinterest_dl.low_level.webdriver.pinterest_driver import PinterestDriver
        from selenium.webdriver.common.by import By
        import copy
        import random
        import socket
        from selenium.common.exceptions import StaleElementReferenceException
        from selenium.webdriver.common.keys import Keys
        from tqdm import tqdm
        from pinterest_dl.data_model.pinterest_media import PinterestMedia

        def patched_scrape(self, url, num=20, timeout=3, verbose=False, ensure_alt=False):
            unique_results = set()
            imgs_data = []
            previous_divs = []
            scroll_count = 0
            no_new_scrolls = 0
            pbar = tqdm(total=num, desc="Scraping")
            try:
                self.webdriver.get(url)
                while scroll_count < 800:
                    try:
                        current_unique = len(unique_results)
                        divs = self.webdriver.find_elements(By.CSS_SELECTOR, "div[data-test-id='pin']")
                        for div in divs:
                            if len(unique_results) >= num:
                                break
                            images = div.find_elements(By.TAG_NAME, "img")
                            href = div.find_element(By.TAG_NAME, "a").get_attribute("href")
                            id = div.get_attribute("data-test-pin-id")
                            if not id:
                                continue
                            for image in images:
                                alt = image.get_attribute("alt")
                                if ensure_alt and (not alt or not alt.strip()):
                                    continue
                                src = image.get_attribute("src")
                                if src and "/236x/" in src:
                                    src = src.replace("/236x/", "/originals/")
                                    if src not in unique_results:
                                        unique_results.add(src)
                                        img_data = PinterestMedia(
                                            int(id),
                                            src,
                                            alt,
                                            href,
                                            resolution=(0, 0),
                                        )
                                        imgs_data.append(img_data)
                                        pbar.update(1)
                                        if len(unique_results) >= num:
                                            break

                        new_in_scroll = len(unique_results) - current_unique
                        if new_in_scroll == 0:
                            no_new_scrolls += 1
                        else:
                            no_new_scrolls = 0
                        if no_new_scrolls >= 10:
                            break

                        previous_divs = copy.copy(divs)

                        # Scroll down
                        dummy = self.webdriver.find_element(By.TAG_NAME, "body")
                        dummy.send_keys(Keys.PAGE_DOWN)
                        self.randdelay(1, 2)
                        scroll_count += 1
                        if scroll_count % 10 == 0:
                            print(f"\nScrolled {scroll_count} times...")

                        # Try to click load more
                        try:
                            load_more = self.webdriver.find_element(By.XPATH, "//button[contains(text(), 'See more') or contains(text(), 'Load more') or contains(@aria-label, 'See more')]")
                            load_more.click()
                            print("Clicked load more button...")
                            time.sleep(2)
                        except:
                            pass

                    except StaleElementReferenceException:
                        if verbose:
                            print("\nStaleElementReferenceException")

            except (socket.error, socket.timeout):
                print("Socket Error")
            finally:
                pbar.close()
                if verbose:
                    print(f"Scraped {len(imgs_data)} images")
            return imgs_data

        PinterestDriver.scrape = patched_scrape

        scraped_ids = set()
        imgs_data = []
        scraped = 0
        batch_limit = limit
        api_instance = PinterestDL.with_browser(
            driver,
            headless=headless,
            incognito=incognito,
            timeout=timeout,
        )
        if st.session_state.use_cookies:
            if not COOKIES_PATH.exists():
                st.session_state['error'] = "No cookies found!"
                return
            api_instance = api_instance.with_cookies_path(COOKIES_PATH)
        scraped_imgs = api_instance.scrape(url, batch_limit)
        for img in scraped_imgs:
            if img.id not in scraped_ids:
                scraped_ids.add(img.id)
                imgs_data.append(img)
                scraped += 1
                if scraped >= limit:
                    break

        # Filter by resolution
        if res_x > 0 or res_y > 0:
            imgs_data = [img for img in imgs_data if img.resolution[0] >= res_x and img.resolution[1] >= res_y]

        # Download
        if imgs_data:
            with st.spinner("Downloading..."):
                from pinterest_dl.low_level.http.downloader import PinterestMediaDownloader
                downloader = PinterestMediaDownloader(user_agent="PinterestDL/0.8.3")
                try:
                    downloader.download_concurrent(
                        imgs_data,
                        project_dir,
                        download_streams=False,
                        num_threads=4,
                        fail_fast=False
                    )
                except Exception as e:
                    error_str = str(e)
                    st.session_state['error'] = f"Download failed: {error_str}"
                    print(f"Download error details: {error_str}")  # Full error to console

            # Log downloaded URLs
            log_file = project_dir / "downloaded_urls.log"
            with open(log_file, "a", encoding="utf-8") as f:
                for img in imgs_data:
                    f.write(f"{img.src}\n")

            # Recursive visual search
            if recurse_factor > 0:
                for img in imgs_data:
                    if str(img.id) == original_pin_id:
                        continue  # Skip the original pin
                    new_project_name = f"20251228_Test_{img.id}"
                    new_project_dir = Path("downloads", new_project_name)
                    new_url = f"https://se.pinterest.com/pin/{img.id}/visual-search/?cropSource=5&entrypoint=closeup_cta&rs=flashlight"
                    print(f"Recursing to visual search for pin {img.id}")
                    scrape_images(
                        url=new_url,
                        project_name=new_project_name,
                        project_dir=new_project_dir,
                        res_x=res_x,
                        res_y=res_y,
                        limit=limit,  # same limit
                        recurse_factor=recurse_factor - 1,
                        timeout=timeout,
                        delay=delay,
                        caption=caption,
                        download_videos=download_videos,
                        use_browser=True,  # force browser for visual search
                        driver=driver,
                        headless=headless,
                        incognito=incognito,
                    )

        # Save cache
        imgs_dict = [img.to_dict() for img in imgs_data]
        io.write_json(imgs_dict, cache_filename, indent=4)

        st.session_state['success'] = "Scrape Complete!"
        print("Done.")
    else:
        api_instance = PinterestDL.with_api(
            timeout=timeout,
            ensure_alt=st.session_state.ensure_cap,
        )
        if st.session_state.use_cookies:
            if not COOKIES_PATH.exists():
                st.session_state['error'] = "No cookies found!"
                return
            api_instance = api_instance.with_cookies_path(COOKIES_PATH)

        try:
            api_instance.scrape_and_download(
                url=url,
                output_dir=project_dir,
                num=limit,
                min_resolution=(res_x, res_y),
                cache_path=cache_filename,
                delay=delay,
                caption=caption,
                download_streams=download_videos,
            )
            st.session_state['success'] = "Scrape Complete!"
        except Exception as e:
            st.session_state['error'] = f"Scrape failed: {str(e)}"
        print("Done.")

        # Log downloaded URLs from cache
        if cache_filename.exists():
            import json
            with open(cache_filename, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            log_file = project_dir / "downloaded_urls.log"
            with open(log_file, "a", encoding="utf-8") as f:
                for item in cached_data:
                    if "url" in item:
                        f.write(f"{item['url']}\n")

        # For API mode, no recursive since no pin IDs available


def search_images(
    query,
    project_name,
    project_dir,
    res_x,
    res_y,
    limit,
    recurse_factor,
    timeout,
    delay,
    caption,
    download_videos,
    use_browser,
    driver,
    headless,
    incognito,
):
    """Search for images using a query and download results."""
    session_time = time.strftime("%Y%m%d%H%M%S")
    cache_path = Path("downloads", "_cache")
    cache_path.mkdir(parents=True, exist_ok=True)
    cache_filename = Path(cache_path, f"{project_name}_{session_time}.json")

    if not query or not project_name:
        st.session_state['error'] = "Please enter a query and Project Name!"
        return

    if project_dir.exists():
        st.session_state['warning'] = "Project already exists! Merge with existing data."

    if use_browser:
        st.session_state['error'] = "Browser scraping not supported for search mode. Please use API mode."
        return

    api_instance = PinterestDL.with_api(
        timeout=timeout,
        ensure_alt=st.session_state.ensure_cap,
    )
    if st.session_state.use_cookies:
        if not COOKIES_PATH.exists():
            st.session_state['error'] = "No cookies found!"
            return
        api_instance = api_instance.with_cookies_path(COOKIES_PATH)

    api_instance.search_and_download(
        query=query,
        output_dir=project_dir,
        num=limit,
        min_resolution=(res_x, res_y),
        cache_path=cache_filename,
        delay=delay,
        caption=caption,
        download_streams=download_videos,
    )
    st.session_state['success'] = "Scrape Complete!"
    print("Done.")

    # Log downloaded URLs from cache
    if cache_filename.exists():
        import json
        with open(cache_filename, "r", encoding="utf-8") as f:
            cached_data = json.load(f)
        log_file = project_dir / "downloaded_urls.log"
        with open(log_file, "a", encoding="utf-8") as f:
            for item in cached_data:
                if "url" in item:
                    f.write(f"{item['url']}\n")


# ========================== Main Application Section ==========================
def main():
    st.set_page_config(page_title="Pinterest DL")
    init_state()
    (
        query,
        project_name,
        res_x,
        res_y,
        image_limit,
        recurse_factor,
        timeout,
        delay,
        mode,
        caption,
        download_videos,
        use_browser,
        driver,
        headless,
        incognito,
    ) = setup_ui()
    project_dir = Path("downloads", project_name)
    footer()

    if "visual-search" in query:
        use_browser = True
        if driver is None:
            driver = "chrome"  # default
        st.info("Visual search URL detected. Using browser scraping automatically.")

    col1, col2 = st.columns([0.5, 2])
    with col1:
        if st.button("Scrape", type="primary"):
            # Clear previous messages
            for key in ['error', 'warning', 'success']:
                if key in st.session_state:
                    del st.session_state[key]
            with st.spinner("Scraping..."):
                if mode == MODE_OPTIONS["Board"]:
                    scrape_images(
                        url=query,
                        project_name=project_name,
                        project_dir=project_dir,
                        res_x=res_x,
                        res_y=res_y,
                        limit=image_limit,
                        recurse_factor=recurse_factor,
                        timeout=timeout,
                        delay=delay,
                        caption=caption,
                        download_videos=download_videos,
                        use_browser=use_browser,
                        driver=driver,
                        headless=headless,
                        incognito=incognito,
                    )
                elif mode == MODE_OPTIONS["Search"]:
                    search_images(
                        query=query,
                        project_name=project_name,
                        project_dir=project_dir,
                        res_x=res_x,
                        res_y=res_y,
                        limit=image_limit,
                        recurse_factor=recurse_factor,
                        timeout=timeout,
                        delay=delay,
                        caption=caption,
                        download_videos=download_videos,
                        use_browser=use_browser,
                        driver=driver,
                        headless=headless,
                        incognito=incognito,
                    )
                else:
                    st.session_state['error'] = "Invalid mode selected!"

    with col2:
        if st.button("📂 Open Directory"):
            if project_dir.exists():
                open_directory(project_dir)
            else:
                st.session_state['warning'] = "Project directory does not exist!"

    # Display messages below buttons
    if 'error' in st.session_state:
        st.error(st.session_state['error'])
    if 'warning' in st.session_state:
        st.warning(st.session_state['warning'])
    if 'success' in st.session_state:
        st.success(st.session_state['success'])


if __name__ == "__main__":
    main()
