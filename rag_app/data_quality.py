"""Conservative runtime gates; raw source artifacts are never rewritten."""
from collections import defaultdict


def review_record(record):
    issues = []
    macros = defaultdict(list)
    for nutrient in record['nutrients']:
        value = nutrient['value']
        unit = nutrient['unit'].lower()
        key = nutrient['key']
        if value is not None:
            if key in {'protein', 'fat', 'carbohydrate'} and unit == 'g':
                macros[key].append(value)
            if record['reference_amount_g'] == 100 and (
                unit == 'g' and value > 100 or key == 'energy' and unit == 'kcal' and value > 1000
            ):
                issues.append('value_exceeds_declared_basis')
            if key in {'vitamin_c', 'beta_caroten'} and unit == 'g':
                issues.append('micronutrient_unit_requires_verification')
        if key and key[0].isdigit():
            issues.append('invalid_nutrient_key')
    if record['reference_amount_g'] == 100 and all(len(macros[k]) == 1 for k in ('protein', 'fat', 'carbohydrate')):
        if sum(macros[k][0] for k in ('protein', 'fat', 'carbohydrate')) > 100.5:
            issues.append('macro_mass_exceeds_declared_basis')
    # The dish export hard-coded 100 g without per-record source evidence.
    # Do not silently reinterpret these records as either 100 g or one serving.
    uncertain_basis = record['dataset'] == 'nin_dishes'
    record['review_status'] = 'quarantined' if issues else 'unreviewed' if uncertain_basis else 'verified'
    record['quality_flags'] = sorted(set(issues))
    record['source_reference_amount_g'] = record['reference_amount_g']
    record['basis_type'] = 'unknown' if uncertain_basis else 'per_100g_edible'
    if uncertain_basis or issues:
        record['reference_amount_g'] = None
        record['basis'] = 'Cơ sở khối lượng/đơn vị đang chờ xác minh; không dùng để tính.'
        for nutrient in record['nutrients']:
            nutrient['source_value'] = nutrient['value']
            nutrient['value'] = None
            nutrient['quality_note'] = 'Số liệu nguồn đang chờ xác minh cơ sở/đơn vị; không dùng để tính.'
    return issues
