"""
Apify Client Wrapper
Centralized client wrapper for managing Apify actor executions,
credit exhaustion error handling, batching, and rate limiting.
"""

import os
import time
import logging
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from apify_client import ApifyClient

# Load environment variables
load_dotenv()

logger = logging.getLogger("ApifyClientWrapper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class ApifyCreditsExhaustedError(Exception):
    """Raised when Apify credits are depleted."""
    pass


class ApifyClientWrapper:
    def __init__(self, api_token: Optional[str] = None):
        self.api_token = api_token or os.getenv("APIFY_API_TOKEN", "")
        if not self.api_token:
            logger.warning("No APIFY_API_TOKEN found in environment. Apify calls will fail if token is required.")
        self.client = ApifyClient(self.api_token) if self.api_token else None

    def get_client(self) -> ApifyClient:
        if not self.client:
            self.api_token = os.getenv("APIFY_API_TOKEN", "")
            if not self.api_token:
                raise ValueError("APIFY_API_TOKEN is missing. Please set it in your .env file.")
            self.client = ApifyClient(self.api_token)
        return self.client

    def run_actor(
        self,
        actor_id: str,
        run_input: Dict[str, Any],
        memory_mbytes: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs an Apify actor and returns all items from the default dataset.
        Handles credit exhaustion error gracefully.
        """
        client = self.get_client()
        logger.info(f"Starting actor {actor_id}...")

        try:
            call_kwargs: Dict[str, Any] = {
                "run_input": run_input,
            }
            if memory_mbytes:
                call_kwargs["memory_mbytes"] = memory_mbytes

            run = client.actor(actor_id).call(**call_kwargs)

            if not run:
                logger.error(f"Actor {actor_id} returned no run response.")
                return []

            if isinstance(run, dict):
                dataset_id = run.get("defaultDatasetId") or run.get("default_dataset_id")
            else:
                dataset_id = getattr(run, "default_dataset_id", None) or getattr(run, "defaultDatasetId", None)

            if not dataset_id:
                logger.warning(f"Actor {actor_id} run completed but has no defaultDatasetId.")
                return []

            dataset_items = list(client.dataset(dataset_id).iterate_items())
            logger.info(f"Actor {actor_id} completed successfully. Retrieved {len(dataset_items)} dataset items.")
            return dataset_items

        except Exception as e:
            err_msg = str(e)
            logger.error(f"Error running actor {actor_id}: {err_msg}")
            
            # Check for Apify credit exhaustion error
            if "exceed your remaining usage" in err_msg.lower() or "credit" in err_msg.lower() and "limit" in err_msg.lower():
                raise ApifyCreditsExhaustedError("Apify credits exhausted: By launching this job you will exceed your remaining usage.") from e
            
            raise e

    def run_actor_in_batches(
        self,
        actor_id: str,
        items: List[Any],
        batch_size: int = 50,
        delay_between_batches: int = 30,
        input_builder: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """
        Processes items in batches (max 50) with a delay between calls.
        """
        all_results = []
        total_batches = (len(items) + batch_size - 1) // batch_size

        for idx in range(0, len(items), batch_size):
            batch_num = (idx // batch_size) + 1
            batch = items[idx : idx + batch_size]
            logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} items) for actor {actor_id}")

            if input_builder:
                run_input = input_builder(batch)
            else:
                run_input = {"items": batch}

            results = self.run_actor(actor_id, run_input)
            all_results.extend(results)

            if idx + batch_size < len(items):
                logger.info(f"Sleeping {delay_between_batches}s between batches to respect rate limits...")
                time.sleep(delay_between_batches)

        return all_results
