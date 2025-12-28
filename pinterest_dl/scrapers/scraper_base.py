import json
import logging
from pathlib import Path
from typing import List, Literal, Optional, Tuple, Union

import tqdm

from pinterest_dl.data_model.pinterest_media import PinterestMedia
from pinterest_dl.exceptions import ExecutableNotFoundError, UnsupportedMediaTypeError
from pinterest_dl.low_level.http import USER_AGENT, downloader
from pinterest_dl.utils import ensure_executable
from pinterest_dl.utils.progress_bar import TqdmProgressBarCallback

logger = logging.getLogger(__name__)


class _ScraperBase:
    def __init__(self):
        pass

    @staticmethod
    def _load_downloaded_registry(output_dir: Path) -> dict:
        """Load the downloaded files registry from JSON file."""
        registry_path = output_dir.parent / "downloaded.json"
        if registry_path.exists():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load downloaded registry: {e}. Starting fresh.")
        return {}

    @staticmethod
    def _save_downloaded_registry(output_dir: Path, registry: dict) -> None:
        """Save the downloaded files registry to JSON file."""
        registry_path = output_dir.parent / "downloaded.json"
        try:
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=4, ensure_ascii=False)
        except IOError as e:
            logger.error(f"Failed to save downloaded registry: {e}")

    @staticmethod
    def download_media(
        media: List[PinterestMedia],
        output_dir: Union[str, Path],
        download_streams: bool,
    ) -> List[PinterestMedia]:
        """Download media from Pinterest using given URLs and fallbacks.

        Args:
            media (List[PinterestMedia]): List of PinterestMedia objects to download.
            output_dir (Union[str, Path]): Directory to store downloaded media.
            download_streams (bool): Whether to download video streams.

        Returns:
            List[PinterestMedia]: List of PinterestMedia objects with local paths set.
        """
        if not isinstance(output_dir, Path):
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load registry of already downloaded files
        registry = _ScraperBase._load_downloaded_registry(output_dir)

        # Filter out already downloaded media
        to_download = []
        for item in media:
            if item.id in registry:
                registered_path = Path(registry[item.id].get("path", ""))
                if registered_path.exists():
                    logger.info(f"Skipping already downloaded: {item.id} at {registered_path}")
                    item.set_local_path(registered_path)
                    continue
                else:
                    # File missing, remove from registry
                    del registry[item.id]
            to_download.append(item)

        if not to_download:
            logger.info("All media already downloaded.")
            return media

        dl = downloader.PinterestMediaDownloader(
            user_agent=USER_AGENT,
            timeout=10,
            max_retries=3,
            progress_callback=TqdmProgressBarCallback(description="Downloading Media"),
        )
        if download_streams:
            try:
                ensure_executable.ensure_executable("ffmpeg")
            except ExecutableNotFoundError as e:
                logger.warning(f"ffmpeg not found: {e}. Falling back to images.")
                print(
                    f"Warning: {e}. Video streams will not be downloaded, falling back to images."
                )
                download_streams = False

        try:
            local_paths = dl.download_concurrent(to_download, output_dir, download_streams)
        except Exception as e:
            # Log the error and re-raise for CLI to handle
            logger.error(f"Download failed: {e}")
            raise

        for item, path in zip(to_download, local_paths):
            item.set_local_path(path)
            # Update registry
            registry[item.id] = {"path": str(path), "downloaded_at": str(Path(path).stat().st_mtime)}
            if item.resolution is None or item.resolution == (0, 0):
                try:
                    item.set_local_resolution(path)
                except FileNotFoundError:
                    print(f"Warning: Local path '{path}' does not exist. Skipping resolution set.")
                except UnsupportedMediaTypeError as ve:
                    print(f"Warning: {ve}. Skipping resolution set for '{path}'.")

        # Save updated registry
        _ScraperBase._save_downloaded_registry(output_dir, registry)

        return media

    @staticmethod
    def add_captions_to_file(
        images: List[PinterestMedia],
        output_dir: Union[str, Path],
        extension: Literal["txt", "json"] = "txt",
        verbose: bool = False,
    ) -> None:
        """Add captions to downloaded images and save them to a file.

        Args:
            images (List[PinterestMedia]): List of PinterestMedia objects to add captions to.
            output_dir (Union[str, Path]): Directory to save image captions.
            extension (Literal["txt","json"]): File extension for the captions.
                'txt' for alt text in separate files,
                'json' for full image data.
            verbose (bool): Enable verbose logging.
            remove_no_alt (bool): Remove images with no alt text.
        """
        if not isinstance(output_dir, Path):
            output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        if verbose:
            print(f"Saving captions to {output_dir}...")
        for img in tqdm.tqdm(images, desc="Captioning to file", disable=verbose):
            if not img.local_path:
                continue
            caption_path = output_dir / f"{img.local_path.stem}.{extension}"
            if caption_path.exists():
                if verbose:
                    print(f"Caption file already exists for {img.local_path}, skipping.")
                continue
            if extension == "json":
                with open(caption_path, "w") as f:
                    f.write(json.dumps(img.to_dict(), indent=4))
            elif extension == "txt":
                if img.alt:
                    with open(caption_path, "w") as f:
                        f.write(img.alt)
                else:
                    if verbose:
                        print(f"No alt text for {img.local_path}")
            else:
                raise ValueError("Invalid file extension. Use 'txt' or 'json'.")
            if verbose:
                print(f"Caption saved for {img.local_path}: '{img.alt}'")

    @staticmethod
    def add_captions_to_meta(images: List[PinterestMedia], verbose: bool = False) -> None:
        """Add captions and origin information to downloaded images.

        Args:
            images (List[PinterestMedia]): List of PinterestMedia objects to add captions to.
            verbose (bool): Enable verbose logging.
        """

        for index in tqdm.tqdm(range(len(images)), desc="Captioning to metadata", disable=verbose):
            img: Optional[PinterestMedia] = None
            try:
                img = images[index]
                if img.video_stream:
                    continue  # Skip streams for metadata captioning
                if not img.local_path:
                    continue
                if img.local_path.suffix == ".gif":
                    if verbose:
                        print(f"Skipping captioning for {img.local_path} (GIF)")
                    continue
                if img.origin:
                    img.meta_write_comment(img.origin)
                    if verbose:
                        print(f"Origin added to {img.local_path}: '{img.origin}'")
                if img.alt:
                    img.meta_write_subject(img.alt)
                    if verbose:
                        print(f"Caption added to {img.local_path}: '{img.alt}'")

            except Exception as e:
                # Log metadata errors but continue processing other images
                if img and img.local_path:
                    logger.warning(
                        f"Failed to add metadata to {img.local_path}: {e}", exc_info=verbose
                    )
                    if verbose:
                        print(f"Error captioning {img.local_path}: {e}")
                else:
                    logger.warning(
                        f"Failed to add metadata to image at index {index}: {e}", exc_info=verbose
                    )

    @staticmethod
    def prune_images(
        images: List[PinterestMedia], min_resolution: Tuple[int, int], verbose: bool = False
    ) -> List[PinterestMedia]:
        """Return images that meet the resolution requirement.

        Args:
            images: Original list of PinterestMedia.
            min_resolution: Minimum (width, height).
            verbose: If True, logs how many were pruned.

        Returns:
            List of PinterestMedia that passed the resolution check.
        """
        kept: List[PinterestMedia] = []
        for img in images:
            if img.prune_local(min_resolution, verbose):
                kept.append(img)

        pruned_count = len(images) - len(kept)
        if verbose:
            print(f"Pruned ({pruned_count}) images")

        return kept
