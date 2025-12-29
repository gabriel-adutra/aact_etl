from typing import Dict, Any, Generator, List
import logging
from .text_parser import TextParser

logger = logging.getLogger(__name__)

class DataCleaner:
    def __init__(self) -> None:
        self.parser = TextParser()


    def clean_study(self, raw_study: Dict[str, Any]) -> Dict[str, Any]:
        study = self._init_study(raw_study)
        self._add_drugs(study, raw_study.get('drugs'))
        self._add_conditions(study, raw_study.get('conditions'))
        self._add_sponsors(study, raw_study.get('sponsors'))
        return study


    def _init_study(self, raw_study: Dict[str, Any]) -> Dict[str, Any]:
        return {
            'nct_id': raw_study.get('nct_id'),
            'title': (raw_study.get('brief_title') or "").strip(),
            'phase': raw_study.get('phase'),
            'status': raw_study.get('overall_status'),
            'drugs': [],
            'conditions': [],
            'sponsors': []
        }


    def _add_drugs(self, study: Dict[str, Any], raw_drugs: Any) -> None:
        if not (raw_drugs and isinstance(raw_drugs, list)):
            return

        for drug in raw_drugs:
            raw_name = drug.get('name')
            if not raw_name:
                continue

            name = raw_name.strip().title()
            description = drug.get('description') or ""
            inferred = self.parser.infer_route_and_form(description)

            study['drugs'].append({
                'name': name,
                'route': inferred['route'],
                'dosage_form': inferred['dosage_form']
            })


    def _add_conditions(self, study: Dict[str, Any], raw_conditions: Any) -> None:
        if not (raw_conditions and isinstance(raw_conditions, list)):
            return

        clean_conds = {c.strip().title() for c in raw_conditions if c}
        study['conditions'] = [{'name': c} for c in clean_conds]
        

    def _add_sponsors(self, study: Dict[str, Any], raw_sponsors: Any) -> None:
        if not (raw_sponsors and isinstance(raw_sponsors, list)):
            return

        for sponsor in raw_sponsors:
            raw_name = sponsor.get('name')
            if not raw_name:
                continue

            name = raw_name.strip()
            study['sponsors'].append({
                'name': name,
                'class': sponsor.get('class')
            })


# TODO:Ideally, this batching helper should be moved to a dedicated module (e.g., transform/batching.py), keeping data_cleaner focused exclusively on data cleaning, while the orchestration of cleaning and batch processing would live in a separate module. However, for this code challenge, I chose to keep the helper in this file, since the transform/batching.py module would contain only this single function, which would merely increase the number of files without providing meaningful benefits to the current pipeline structure.
def batch_cleaned_trials(trials_stream: Generator[Dict[str, Any], None, None], data_cleaner: DataCleaner, batch_size: int, limit: int) -> Generator[List[Dict[str, Any]], None, None]:
    batch = []
    processed = 0

    for raw_trial in trials_stream:
        processed += 1
        if processed > limit:
            break

        clean_trial = data_cleaner.clean_study(raw_trial)
        batch.append(clean_trial)

        if len(batch) >= batch_size:
            logger.info(f"Processed and cleaned {processed} trials so far. Ready to load batch of {len(batch)} trials.")
            yield batch
            batch = []

    if batch:
        logger.info(f"Processed and cleaned {processed} trials total. Ready to load final batch of {len(batch)} trials.")
        yield batch