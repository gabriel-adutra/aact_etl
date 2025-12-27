#!/usr/bin/env python3
import sys
import os
import logging

# Suppress logging from modules
logging.basicConfig(level=logging.WARNING)

# Ensure src is on path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.extract.aact_client import AACTClient
from src.transform.text_parser import TextParser
from src.transform.data_cleaner import DataCleaner
from src.load.neo4j_client import Neo4jClient


def print_header(title):
    print("=" * 80)
    print(title)
    print("=" * 80)


def print_step(step_num, total_steps, message):
    print(f"\n[{step_num}/{total_steps}] {message}")


def print_section(title):
    print(f"\n{title}")
    print("-" * 80)


def print_analysis_results(stats, percentages):
    print_step(4, 4, "Source Analysis (AACT):")
    print_section("Drug Description Coverage")
    print(f"Total Trial-Drug relationships: {stats['total_trial_drug_relations']:,}")
    print(f"  * Without drug description (null): {stats['drugs_without_description']:,} ({percentages['pct_no_desc']:.1f}%)")
    print(f"  * Empty drug description: {stats['drugs_with_empty_description']:,} ({percentages['pct_empty_desc']:.1f}%)")
    print(f"  * With drug description: {stats['drugs_with_description']:,} ({percentages['pct_with_desc']:.1f}%)")
    
    print_section("Inferences from drug descriptions")
    print(f"  * Route inferred: {stats['drugs_with_route_inferred']:,} ({percentages['pct_route']:.2f}% of total, {percentages['pct_route_from_desc']:.1f}% of those with drug description)")
    print(f"  * Dosage_form inferred: {stats['drugs_with_dosage_form_inferred']:,} ({percentages['pct_dosage_form']:.2f}% of total, {percentages['pct_dosage_form_from_desc']:.1f}% of those with drug description)")
    print(f"  * Both inferred: {stats['drugs_with_both_inferred']:,} ({percentages['pct_both']:.2f}% of total, {percentages['pct_both_from_desc']:.1f}% of those with drug description)")


def get_neo4j_stats(neo4j_client):
    with neo4j_client.driver.session() as session:
        # Total STUDIED_IN relationships
        total_rel = session.run("MATCH ()-[r:STUDIED_IN]->() RETURN count(r) AS total").single()["total"]
        
        # With route inferred
        route_rel = session.run(
            "MATCH ()-[r:STUDIED_IN]->() WHERE r.route IS NOT NULL AND r.route <> 'Unknown' RETURN count(r) AS total"
        ).single()["total"]
        
        # With dosage_form inferred
        dosage_form_rel = session.run(
            "MATCH ()-[r:STUDIED_IN]->() WHERE r.dosage_form IS NOT NULL AND r.dosage_form <> 'Unknown' RETURN count(r) AS total"
        ).single()["total"]
        
        # With both inferred
        both_rel = session.run(
            """MATCH ()-[r:STUDIED_IN]->() 
               WHERE (r.route IS NOT NULL AND r.route <> 'Unknown') 
                 AND (r.dosage_form IS NOT NULL AND r.dosage_form <> 'Unknown') 
               RETURN count(r) AS total"""
        ).single()["total"]
        
        # With any inference
        any_rel = session.run(
            """MATCH ()-[r:STUDIED_IN]->() 
               WHERE (r.route IS NOT NULL AND r.route <> 'Unknown') 
                  OR (r.dosage_form IS NOT NULL AND r.dosage_form <> 'Unknown') 
               RETURN count(r) AS total"""
        ).single()["total"]
        
        return {
            'total_relationships': total_rel,
            'with_route': route_rel,
            'with_dosage_form': dosage_form_rel,
            'with_both': both_rel,
            'with_any_inference': any_rel
        }


def analyze_trial_drugs(raw_trial, parser):
    stats = {
        'total': 0,
        'without_description': 0,
        'empty_description': 0,
        'with_description': 0,
        'route_inferred': 0,
        'dosage_form_inferred': 0,
        'both_inferred': 0
    }
    
    for drug in raw_trial.get('drugs', []):
        stats['total'] += 1
        description = drug.get('description')
        
        if description is None:
            stats['without_description'] += 1
        elif not description.strip():
            stats['empty_description'] += 1
        else:
            stats['with_description'] += 1
            inferred = parser.infer_route_and_form(description)
            
            has_route = inferred['route'] != 'Unknown'
            has_dosage_form = inferred['dosage_form'] != 'Unknown'
            
            if has_route:
                stats['route_inferred'] += 1
            if has_dosage_form:
                stats['dosage_form_inferred'] += 1
            if has_route and has_dosage_form:
                stats['both_inferred'] += 1
    
    return stats


def extract_trials(postgres_fetch_size=100):
    print_step(1, 4, "Extracting data from AACT...")
    aact = AACTClient()
    return aact.fetch_trials(postgres_fetch_size=postgres_fetch_size)


def analyze_trials_stream(trials_stream, parser, limit=1000):
    aggregated_stats = {
        'total_trial_drug_relations': 0,
        'drugs_without_description': 0,
        'drugs_with_empty_description': 0,
        'drugs_with_description': 0,
        'drugs_with_route_inferred': 0,
        'drugs_with_dosage_form_inferred': 0,
        'drugs_with_both_inferred': 0
    }
    
    processed = 0
    raw_trials = []
    
    for raw_trial in trials_stream:
        processed += 1
        if processed > limit:
            break
        
        trial_stats = analyze_trial_drugs(raw_trial, parser)
        aggregated_stats['total_trial_drug_relations'] += trial_stats['total']
        aggregated_stats['drugs_without_description'] += trial_stats['without_description']
        aggregated_stats['drugs_with_empty_description'] += trial_stats['empty_description']
        aggregated_stats['drugs_with_description'] += trial_stats['with_description']
        aggregated_stats['drugs_with_route_inferred'] += trial_stats['route_inferred']
        aggregated_stats['drugs_with_dosage_form_inferred'] += trial_stats['dosage_form_inferred']
        aggregated_stats['drugs_with_both_inferred'] += trial_stats['both_inferred']
        
        raw_trials.append(raw_trial)
    
    return aggregated_stats, raw_trials


def clean_trials_batches(raw_trials, data_cleaner, batch_size=500):
    print_step(2, 4, "Cleaning trials...")
    clean_batches = []
    raw_trials_batch = []
    
    for raw_trial in raw_trials:
        raw_trials_batch.append(raw_trial)
        
        if len(raw_trials_batch) >= batch_size:
            clean_batch = [data_cleaner.clean_study(t) for t in raw_trials_batch]
            clean_batches.append(clean_batch)
            raw_trials_batch = []
    
    if raw_trials_batch:
        clean_batch = [data_cleaner.clean_study(t) for t in raw_trials_batch]
        clean_batches.append(clean_batch)
    
    return clean_batches


def load_trials_to_neo4j(clean_batches):
    neo4j = Neo4jClient()
    neo4j.ensure_graph_schema()
    
    for clean_batch in clean_batches:
        if clean_batch:
            neo4j.load_trials_batch(clean_batch)
    
    return neo4j


def calculate_percentages(stats):
    total = stats['total_trial_drug_relations']
    with_desc = stats['drugs_with_description']
    
    return {
        'pct_no_desc': (stats['drugs_without_description'] / total * 100) if total > 0 else 0,
        'pct_empty_desc': (stats['drugs_with_empty_description'] / total * 100) if total > 0 else 0,
        'pct_with_desc': (with_desc / total * 100) if total > 0 else 0,
        'pct_route': (stats['drugs_with_route_inferred'] / total * 100) if total > 0 else 0,
        'pct_dosage_form': (stats['drugs_with_dosage_form_inferred'] / total * 100) if total > 0 else 0,
        'pct_both': (stats['drugs_with_both_inferred'] / total * 100) if total > 0 else 0,
        'pct_route_from_desc': (stats['drugs_with_route_inferred'] / with_desc * 100) if with_desc > 0 else 0,
        'pct_dosage_form_from_desc': (stats['drugs_with_dosage_form_inferred'] / with_desc * 100) if with_desc > 0 else 0,
        'pct_both_from_desc': (stats['drugs_with_both_inferred'] / with_desc * 100) if with_desc > 0 else 0
    }


def compare_with_neo4j(neo4j_stats, aact_stats):
    print_header("VALIDATION: Comparison with Neo4j")
    
    print(f"Relationships in Neo4j: {neo4j_stats['total_relationships']:,}")
    print(f"Expected relationships (AACT): {aact_stats['total_trial_drug_relations']:,}")
    
    match_total = "OK" if neo4j_stats['total_relationships'] == aact_stats['total_trial_drug_relations'] else "X"
    match_route = "OK" if neo4j_stats['with_route'] == aact_stats['drugs_with_route_inferred'] else "X"
    match_dosage_form = "OK" if neo4j_stats['with_dosage_form'] == aact_stats['drugs_with_dosage_form_inferred'] else "X"
    match_both = "OK" if neo4j_stats['with_both'] == aact_stats['drugs_with_both_inferred'] else "X"
    
    print_section("Comparison")
    print(f"  {match_total} Total relationships: Neo4j={neo4j_stats['total_relationships']:,} vs AACT={aact_stats['total_trial_drug_relations']:,}")
    print(f"  {match_route} Route inferred: Neo4j={neo4j_stats['with_route']:,} vs AACT={aact_stats['drugs_with_route_inferred']:,}")
    print(f"  {match_dosage_form} Dosage_form inferred: Neo4j={neo4j_stats['with_dosage_form']:,} vs AACT={aact_stats['drugs_with_dosage_form_inferred']:,}")
    print(f"  {match_both} Both inferred: Neo4j={neo4j_stats['with_both']:,} vs AACT={aact_stats['drugs_with_both_inferred']:,}")
    
    if match_total == "X" or match_route == "X" or match_dosage_form == "X" or match_both == "X":
        print("\nWARNING: There are discrepancies between AACT and Neo4j!")
    else:
        print("\nOK Validation: All numbers match!")
    
    print("=" * 80)


def analyze_inference_coverage():
    print_header("COMPLETE COVERAGE AND INFERENCE ANALYSIS")
    
    trials_stream = extract_trials()
    
    text_parser = TextParser()
    aact_stats, raw_trials = analyze_trials_stream(trials_stream, text_parser)
    
    data_cleaner = DataCleaner()
    clean_batches = clean_trials_batches(raw_trials, data_cleaner)
    
    neo4j = load_trials_to_neo4j(clean_batches)
    
    print_step(3, 4, "Connecting to Neo4j for validation...")
    neo4j_stats = get_neo4j_stats(neo4j)
    neo4j.close_connection()
    
    percentages = calculate_percentages(aact_stats)
    print_analysis_results(aact_stats, percentages)
    compare_with_neo4j(neo4j_stats, aact_stats)


if __name__ == "__main__":
    try:
        analyze_inference_coverage()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

