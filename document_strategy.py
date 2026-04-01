from typing import List, Dict, Any, Tuple
import re
from datetime import datetime
from document_types import DocumentType, DOCUMENT_FIELDS
from mrz_parser import MRZParser
from cin_layouts import detect_cin_layout, get_zone

class DocumentStrategy:
    """
    Extraction spécifique selon le type de document
    """

    @staticmethod
    def _has_non_empty_value(extracted: Dict[str, Any], field: str) -> bool:
        """Vérifie qu'un champ existe avec une valeur non vide."""
        field_data = extracted.get(field)
        if not isinstance(field_data, dict):
            return False
        value = field_data.get("value")
        return isinstance(value, str) and bool(value.strip())

    @staticmethod
    def _parse_ddmmyyyy(value: str) -> Any:
        """Parse une date DD/MM/YYYY en datetime, sinon None."""
        if not isinstance(value, str):
            return None

        match = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', value.strip())
        if not match:
            return None

        day, month, year = map(int, match.groups())
        try:
            return datetime(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _extract_year_candidates(blocks: List[Dict[str, Any]]) -> List[int]:
        """Extrait les annees plausibles (1900-2099) depuis les blocs OCR."""
        years = []
        for block in blocks:
            text = str(block.get("text", "")).upper().replace('O', '0')
            for m in re.finditer(r'\b((?:19|20)\d{2})\b', text):
                years.append(int(m.group(1)))
        return years

    @staticmethod
    def _text_has_label(text: str, label: str) -> bool:
        """Match robuste des labels: évite les faux positifs sur labels courts (ex: NOM dans PRENOMS)."""
        text_u = (text or "").upper()
        label_u = (label or "").upper()
        if not text_u or not label_u:
            return False

        # Labels très courts -> matching sur frontière de mot alphabétique.
        if len(label_u) <= 4 and label_u.isalpha():
            return bool(re.search(rf'(?<![A-Z]){re.escape(label_u)}(?![A-Z])', text_u))

        return label_u in text_u

    @staticmethod
    def _normalize_text(value: str) -> str:
        """Normalise une chaine pour matching OCR tolerant."""
        if not isinstance(value, str):
            return ""
        return re.sub(r"[^A-Z0-9]", "", value.upper())

    @staticmethod
    def _is_plausible_person_name(value: str, forbidden_tokens: set = None) -> bool:
        """Vérifie qu'une valeur ressemble à un nom/prénom humain et non à un artefact OCR/MRZ."""
        if not isinstance(value, str):
            return False

        raw = value.strip().upper()
        if len(raw) < 2 or len(raw) > 40:
            return False

        # Les noms ne doivent pas contenir de chiffres ni de séparateurs MRZ.
        if any(ch.isdigit() for ch in raw):
            return False
        if '<' in raw or '/' in raw or '\\' in raw:
            return False

        compact = re.sub(r"[^A-Z]", "", raw)
        if len(compact) < 2:
            return False

        # Rejeter les textes majoritairement non alphabétiques.
        alpha_ratio = len(compact) / max(len(raw.replace(" ", "")), 1)
        if alpha_ratio < 0.75:
            return False

        if forbidden_tokens:
            tokens = set(re.findall(r"[A-Z]+", raw))
            if tokens & forbidden_tokens:
                return False

        return True

    @staticmethod
    def _compute_blocks_extent(blocks: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
        """Calcule les bornes globales (min_x, min_y, max_x, max_y) des bbox OCR."""
        xs = []
        ys = []
        for block in blocks:
            bbox = block.get("bbox") or []
            for point in bbox:
                if isinstance(point, list) and len(point) == 2:
                    xs.append(float(point[0]))
                    ys.append(float(point[1]))

        if not xs or not ys:
            return 0.0, 0.0, 1.0, 1.0
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _bbox_to_normalized(bbox: List[List[float]], extent: Tuple[float, float, float, float]) -> List[List[float]]:
        """Convertit une bbox en coordonnees normalisees [0,1]."""
        min_x, min_y, max_x, max_y = extent
        width = max(max_x - min_x, 1e-6)
        height = max(max_y - min_y, 1e-6)

        normalized = []
        for point in bbox:
            if not isinstance(point, list) or len(point) != 2:
                continue
            x, y = float(point[0]), float(point[1])
            normalized.append([
                max(0.0, min(1.0, (x - min_x) / width)),
                max(0.0, min(1.0, (y - min_y) / height)),
            ])
        return normalized

    @staticmethod
    def _bbox_center(normalized_bbox: List[List[float]]) -> Tuple[float, float]:
        if not normalized_bbox:
            return 0.0, 0.0
        x_vals = [p[0] for p in normalized_bbox]
        y_vals = [p[1] for p in normalized_bbox]
        return (sum(x_vals) / len(x_vals), sum(y_vals) / len(y_vals))

    @staticmethod
    def _point_in_zone(point: Tuple[float, float], zone: Tuple[float, float, float, float]) -> bool:
        x, y = point
        x1, y1, x2, y2 = zone
        return x1 <= x <= x2 and y1 <= y <= y2

    @staticmethod
    def _find_block_for_field(blocks: List[Dict[str, Any]], field_value: str) -> Dict[str, Any]:
        """Retrouve le bloc OCR le plus probable pour une valeur de champ."""
        target = DocumentStrategy._normalize_text(field_value)
        if not target:
            return {}

        # Eviter les matchs parasites sur tokens OCR tres courts (ex: "0", "03").
        if len(target) < 3:
            return {}

        best = None
        best_score = -1.0
        for block in blocks:
            text = str(block.get("text", ""))
            normalized_text = DocumentStrategy._normalize_text(text)
            if not normalized_text:
                continue

            if len(normalized_text) < 3:
                continue

            score = 0.0
            if target == normalized_text:
                score += 1.3
            elif target in normalized_text and len(target) >= 6:
                score += 1.0
            elif normalized_text in target and len(normalized_text) >= 6:
                score += 0.9
            elif target[:8] and len(target) >= 8 and target[:8] in normalized_text:
                score += 0.6

            if score == 0.0:
                # Matching tolerant pour dates OCR (ex: 2/01/2023 vs 01/02/2023).
                target_date = re.search(r'(\d{1,2})\D(\d{1,2})\D((?:19|20)\d{2})', str(field_value))
                block_date = re.search(r'(\d{1,2})\D(\d{1,2})\D((?:19|20)\d{2})', text)
                if target_date and block_date:
                    td1, tm1, ty = target_date.groups()
                    bd1, bm1, by = block_date.groups()
                    if ty == by and {int(td1), int(tm1)} == {int(bd1), int(bm1)}:
                        score += 0.95

            if score == 0.0:
                continue

            score += float(block.get("confidence", 0.0)) * 0.2

            if score > best_score:
                best = block
                best_score = score

        return best if best_score >= 0.6 and isinstance(best, dict) else {}

    @staticmethod
    def _annotate_cin_locations(extracted: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ajoute la localisation detectee et zone attendue par pays pour les champs CIN."""
        if not extracted or not blocks:
            return extracted

        full_text = " ".join(str(b.get("text", "")) for b in blocks)
        extent = DocumentStrategy._compute_blocks_extent(blocks)

        cin_fields = [
            "numero_id",
            "nom",
            "prenom",
            "date_naissance",
            "date_delivrance",
            "date_expiration",
        ]

        field_centers = {}
        field_blocks = {}
        for field in cin_fields:
            field_data = extracted.get(field)
            if not isinstance(field_data, dict):
                continue

            value = field_data.get("value", "")
            if not isinstance(value, str) or not value.strip():
                continue

            matched_block = DocumentStrategy._find_block_for_field(blocks, value)
            if not matched_block:
                continue

            raw_bbox = matched_block.get("bbox") or []
            normalized_bbox = DocumentStrategy._bbox_to_normalized(raw_bbox, extent)
            center = DocumentStrategy._bbox_center(normalized_bbox)

            field_centers[field] = center
            field_blocks[field] = {
                "block": matched_block,
                "bbox": raw_bbox,
                "normalized_bbox": normalized_bbox,
                "center": center,
            }

        selected_layout = detect_cin_layout(full_text, field_centers)
        template_id = str(selected_layout.get("template_id", "GENERIC_CIN_V1"))
        country = str(selected_layout.get("country", "GENERIC"))
        version = str(selected_layout.get("version", "GENERIC_V1"))
        template_score = float(selected_layout.get("score", 0.0))

        for field in cin_fields:
            field_data = extracted.get(field)
            if not isinstance(field_data, dict):
                continue

            zone = get_zone(template_id, field)

            location = {
                "template_id": template_id,
                "country_template": country,
                "layout_version": version,
                "template_score": template_score,
                "expected_zone": list(zone) if zone else None,
                "in_expected_zone": False,
            }

            field_block = field_blocks.get(field)
            if field_block:
                matched_block = field_block["block"]
                raw_bbox = field_block["bbox"]
                normalized_bbox = field_block["normalized_bbox"]
                center = field_block["center"]

                location.update({
                    "block_id": matched_block.get("id"),
                    "bbox": raw_bbox,
                    "normalized_bbox": normalized_bbox,
                    "center": [round(center[0], 4), round(center[1], 4)],
                })

                if zone:
                    location["in_expected_zone"] = DocumentStrategy._point_in_zone(center, zone)

            field_data["location"] = location

        return extracted

    @staticmethod
    def _extract_all_dates(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extrait TOUTES les dates du document (formats numériques et mois texte)
        Retourne une liste triée chronologiquement de toutes les dates trouvées
        """
        dates_found = []

        month_map = {
            # EN
            'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04', 'MAY': '05', 'JUN': '06',
            'JUL': '07', 'AUG': '08', 'SEP': '09', 'SEPT': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12',
            # FR
            'JANV': '01', 'FEV': '02', 'FEVR': '02', 'MARS': '03', 'AVR': '04', 'MAI': '05',
            'JUIN': '06', 'JUIL': '07', 'AOUT': '08', 'SEPTEMBRE': '09', 'OCTOBRE': '10',
            'NOVEMBRE': '11', 'DECEMBRE': '12',
        }

        def _resolve_month_number(token: str) -> str:
            """Résout un mois OCR sans règles spécifiques au dataset."""
            if not token:
                return ""

            # Normalisation OCR générique: chiffres souvent confondus avec lettres.
            cleaned = re.sub(r'[^A-Z0-9]', '', token.upper())
            cleaned = (
                cleaned
                .replace('0', 'O')
                .replace('1', 'I')
                .replace('5', 'S')
            )

            if cleaned in month_map:
                return month_map[cleaned]

            # Fallback générique par préfixe (>= 3) pour capter les mois tronqués OCR.
            if len(cleaned) >= 3:
                candidates = [v for k, v in month_map.items() if k.startswith(cleaned) or cleaned.startswith(k)]
                if candidates:
                    # Dédupliquer tout en conservant l'ordre.
                    unique = list(dict.fromkeys(candidates))
                    if len(unique) == 1:
                        return unique[0]

            return ""

        def _append_date(day: int, month: int, year: int, conf: float, block_id: int) -> bool:
            try:
                if year < 100:
                    year = _normalize_two_digit_year(year)
                date_obj = datetime(year, month, day)
                dates_found.append({
                    "value": f"{day:02d}/{month:02d}/{year}",
                    "date_obj": date_obj,
                    "confidence": conf,
                    "block_id": block_id
                })
                return True
            except ValueError:
                return False

        def _normalize_two_digit_year(year_2d: int) -> int:
            # Heuristique stable pour documents d'identite:
            # 00-29 -> 2000-2029, 30-99 -> 1930-1999.
            return 2000 + year_2d if year_2d <= 29 else 1900 + year_2d
        
        for block in blocks:
            text = block["text"]
            conf = block.get("confidence", 0.8)
            block_id = block.get("id", -1)
            text_upper_raw = text.upper()
            text_upper_num = text_upper_raw.replace('O', '0')

            # Chercher format MM/DD/YYYY ou DD/MM/YYYY
            date_matches = re.findall(r'(\d{1,2})/(\d{1,2})/(\d{4})', text_upper_num)
            
            for match in date_matches:
                month_or_day1, day_or_month2, year = match
                m1, d2, y = int(month_or_day1), int(day_or_month2), int(year)

                # Priorite au format DD/MM/YYYY dans ce pipeline majoritairement francophone.
                if _append_date(m1, d2, y, conf, block_id):
                    continue

                # Fallback format US MM/DD/YYYY.
                _append_date(d2, m1, y, conf, block_id)

            # Format DD/MM/YY ou MM/DD/YY (OCR tronque souvent l'annee)
            short_year_matches = re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{2})\b', text_upper_num)
            for a, b, yy in short_year_matches:
                d1, d2, y2 = int(a), int(b), _normalize_two_digit_year(int(yy))

                if _append_date(d1, d2, y2, conf, block_id):
                    continue

                _append_date(d2, d1, y2, conf, block_id)

            # OCR bruité fréquent: DD/MMYYYY (ex: 12/012023)
            noisy_matches = re.findall(r'\b(\d{1,2})[\./-](\d{2})((?:19|20)\d{2})\b', text_upper_num)
            for day, month, year in noisy_matches:
                _append_date(int(day), int(month), int(year), conf, block_id)

            # OCR très bruité: DD/MMY... avec chiffre parasite avant l'annee
            # Ex: 16/0911983 -> day=16, month=09, year=1983 (on garde les 4 derniers chiffres)
            noisy_year_tail_matches = re.findall(r'\b(\d{1,2})[\./-](\d{2})(\d{4,5})\b', text_upper_num)
            for day, month, year_tail in noisy_year_tail_matches:
                year = int(year_tail[-4:])
                _append_date(int(day), int(month), year, conf, block_id)

            # Format compact DDMMYYYY
            for compact in re.findall(r'\b(\d{2})(\d{2})((?:19|20)\d{2})\b', text_upper_num):
                day, month, year = compact
                _append_date(int(day), int(month), int(year), conf, block_id)

            # Format mois texte: 14JAN/JAN2033, 14JAN2033, 14 JAN 2033, 14.MAY 2029,
            # mais aussi années OCR sur 2 chiffres (ex: 23SEPT/SEP25).
            for m in re.finditer(r'(\d{1,2})\s*[\.-]?\s*([A-Z0-9]{2,5})\s*/?\s*[A-Z0-9]{0,10}\s*((?:(?:19|20)\d{2})|(?:\d{2}))\b', text_upper_raw):
                day, mon_abbr, year_raw = m.groups()
                month_num = _resolve_month_number(mon_abbr)
                if month_num:
                    if len(year_raw) == 2:
                        year = _normalize_two_digit_year(int(year_raw))
                    else:
                        year = int(year_raw)
                    _append_date(int(day), int(month_num), year, conf, block_id)

            # Format abrégé sans séparateur: 21OCT26, 07JUN24, 03AOUT21.
            for m in re.finditer(r'\b(\d{1,2})([A-Z0-9]{3,5})(\d{2,4})\b', text_upper_raw):
                day, mon_abbr, year_raw = m.groups()
                month_num = _resolve_month_number(mon_abbr)
                if not month_num:
                    continue
                if len(year_raw) == 2:
                    year = _normalize_two_digit_year(int(year_raw))
                else:
                    year = int(year_raw)
                _append_date(int(day), int(month_num), year, conf, block_id)

            # Format MMYYYY ou MM/YYYY (utile pour dates délivrance/expiration)
            for m in re.finditer(r'\b(0[1-9]|1[0-2])\s*/?\s*((?:19|20)\d{2})\b', text_upper_num):
                month, year = m.groups()
                _append_date(1, int(month), int(year), conf, block_id)
        
        # Trier par date chronologique
        if dates_found:
            # Déduplication par valeur en gardant la meilleure confiance
            best_by_value = {}
            for item in dates_found:
                value = item["value"]
                if value not in best_by_value or item["confidence"] > best_by_value[value]["confidence"]:
                    best_by_value[value] = item
            dates_found = sorted(best_by_value.values(), key=lambda x: x["date_obj"])
        
        return dates_found
    
    @staticmethod
    def _assign_dates_intelligently(extracted: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Assigne intelligemment les dates trouvées pour les champs MANQUANTS:
        - Plus ancienne → date_naissance
        - Date du milieu → date_delivrance  
        - Plus récente → date_expiration
        
        IMPORTANT: Ne réassigne QUE les champs vides!
        """
        # Vérifier quels champs de dates sont déjà remplis
        has_naissance = DocumentStrategy._has_non_empty_value(extracted, 'date_naissance')
        has_delivrance = DocumentStrategy._has_non_empty_value(extracted, 'date_delivrance')
        has_expiration = DocumentStrategy._has_non_empty_value(extracted, 'date_expiration')
        
        # Si tous les champs de dates sont remplis, pas besoin de réassigner
        if has_naissance and has_delivrance and has_expiration:
            return extracted
        
        # Trouver toutes les dates
        all_dates = DocumentStrategy._extract_all_dates(blocks)
        
        if not all_dates:
            return extracted
        
        # Construire un ensemble de dates déjà utilisées (pour éviter les doublons)
        used_dates_str = set()
        for field in ['date_naissance', 'date_delivrance', 'date_expiration']:
            if DocumentStrategy._has_non_empty_value(extracted, field):
                used_dates_str.add(extracted[field]['value'])
        
        # Filtrer les dates déjà utilisées
        remaining_dates = [d for d in all_dates if d['value'] not in used_dates_str]
        
        if not remaining_dates:
            return extracted
        
        missing_fields = [
            field for field in ['date_naissance', 'date_delivrance', 'date_expiration']
            if not DocumentStrategy._has_non_empty_value(extracted, field)
        ]

        birth_anchor = DocumentStrategy._parse_ddmmyyyy(
            extracted.get('date_naissance', {}).get('value', '')
        ) if DocumentStrategy._has_non_empty_value(extracted, 'date_naissance') else None
        delivery_anchor = DocumentStrategy._parse_ddmmyyyy(
            extracted.get('date_delivrance', {}).get('value', '')
        ) if DocumentStrategy._has_non_empty_value(extracted, 'date_delivrance') else None
        expiration_anchor = DocumentStrategy._parse_ddmmyyyy(
            extracted.get('date_expiration', {}).get('value', '')
        ) if DocumentStrategy._has_non_empty_value(extracted, 'date_expiration') else None

        def _set_field(field: str, date_item: Dict[str, Any], method: str) -> None:
            extracted[field] = {
                "value": date_item["value"],
                "confidence": date_item.get("confidence", 0.8),
                "method": method,
            }

        # Cas 1: un seul champ manquant -> choisir intelligemment selon le champ.
        if len(missing_fields) == 1 and remaining_dates:
            target = missing_fields[0]

            if target == 'date_naissance':
                _set_field(target, remaining_dates[0], "chronology_single_oldest")
            elif target == 'date_expiration':
                _set_field(target, remaining_dates[-1], "chronology_single_newest")
            else:
                # date_delivrance manquante: privilégier une date entre naissance et expiration si possible.
                between = [
                    d for d in remaining_dates
                    if (birth_anchor is None or d['date_obj'] >= birth_anchor)
                    and (expiration_anchor is None or d['date_obj'] <= expiration_anchor)
                ]
                chosen = between[0] if between else remaining_dates[min(1, len(remaining_dates) - 1)]
                _set_field(target, chosen, "chronology_single_middle")

        # Cas 2: deux champs manquants -> utiliser les ancres existantes pour limiter les inversions.
        elif len(missing_fields) == 2 and remaining_dates:
            missing_set = set(missing_fields)

            if missing_set == {'date_delivrance', 'date_expiration'}:
                candidates = [d for d in remaining_dates if birth_anchor is None or d['date_obj'] >= birth_anchor]
                if not candidates:
                    candidates = remaining_dates
                _set_field('date_delivrance', candidates[0], "chronology_pair_delivery")
                _set_field('date_expiration', candidates[-1], "chronology_pair_expiration")

            elif missing_set == {'date_naissance', 'date_delivrance'}:
                candidates = [d for d in remaining_dates if expiration_anchor is None or d['date_obj'] <= expiration_anchor]
                if not candidates:
                    candidates = remaining_dates
                _set_field('date_naissance', candidates[0], "chronology_pair_birth")
                _set_field('date_delivrance', candidates[-1], "chronology_pair_delivery")

            else:
                # naissance + expiration manquantes
                _set_field('date_naissance', remaining_dates[0], "chronology_pair_birth")
                _set_field('date_expiration', remaining_dates[-1], "chronology_pair_expiration")

        # Cas 3: trois champs manquants ou plus de dates disponibles.
        elif len(remaining_dates) >= 3:
            if not has_naissance:
                _set_field('date_naissance', remaining_dates[0], "chronology_oldest")
            if not has_delivrance:
                # Prendre une date intermédiaire stable même si plus de 3 dates existent.
                mid_index = len(remaining_dates) // 2
                _set_field('date_delivrance', remaining_dates[mid_index], "chronology_middle")
            if not has_expiration:
                _set_field('date_expiration', remaining_dates[-1], "chronology_newest")

        # Cas 4: fallback minimal quand il reste des dates mais logique précédente non déclenchée.
        elif remaining_dates:
            if not has_naissance:
                _set_field('date_naissance', remaining_dates[0], "chronology_fallback")
            if not has_delivrance and len(remaining_dates) >= 2:
                _set_field('date_delivrance', remaining_dates[0], "chronology_fallback")
            if not has_expiration:
                _set_field('date_expiration', remaining_dates[-1], "chronology_fallback")

        return DocumentStrategy._enforce_date_consistency(extracted, blocks)

    @staticmethod
    def _enforce_date_consistency(extracted: Dict[str, Any], blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Répare les incohérences de chronologie: naissance <= délivrance <= expiration."""
        current_year = datetime.utcnow().year

        parsed = {}
        for field in ['date_naissance', 'date_delivrance', 'date_expiration']:
            if DocumentStrategy._has_non_empty_value(extracted, field):
                parsed[field] = DocumentStrategy._parse_ddmmyyyy(extracted[field]['value'])

        all_dates = DocumentStrategy._extract_all_dates(blocks)
        by_value = {d['value']: d for d in all_dates}

        for field in ['date_naissance', 'date_delivrance', 'date_expiration']:
            if DocumentStrategy._has_non_empty_value(extracted, field):
                value = extracted[field]['value']
                date_obj = DocumentStrategy._parse_ddmmyyyy(value)
                if date_obj and value not in by_value:
                    by_value[value] = {
                        'value': value,
                        'date_obj': date_obj,
                        'confidence': extracted[field].get('confidence', 0.8),
                        'block_id': -1
                    }

        if not by_value:
            return extracted

        unique_dates = sorted(by_value.values(), key=lambda x: x['date_obj'])

        birth = parsed.get('date_naissance')
        delivery = parsed.get('date_delivrance')
        expiration = parsed.get('date_expiration')

        needs_repair = (
            (birth and birth.year > current_year) or
            (birth and expiration and birth > expiration) or
            (birth and delivery and delivery < birth) or
            (delivery and expiration and delivery > expiration)
        )

        if not needs_repair:
            return extracted

        # Réparation simple et robuste basée sur l'ordre chronologique global.
        birth_candidate = next((d for d in unique_dates if d['date_obj'].year <= current_year), unique_dates[0])
        expiration_candidate = unique_dates[-1]

        extracted['date_naissance'] = {
            'value': birth_candidate['value'],
            'confidence': birth_candidate.get('confidence', 0.8),
            'method': 'chronology_repair_birth'
        }

        extracted['date_expiration'] = {
            'value': expiration_candidate['value'],
            'confidence': expiration_candidate.get('confidence', 0.8),
            'method': 'chronology_repair_expiration'
        }

        between_candidates = [
            d for d in unique_dates
            if birth_candidate['date_obj'] <= d['date_obj'] <= expiration_candidate['date_obj']
            and d['value'] not in {birth_candidate['value'], expiration_candidate['value']}
        ]
        if between_candidates:
            delivery_candidate = between_candidates[0]
            extracted['date_delivrance'] = {
                'value': delivery_candidate['value'],
                'confidence': delivery_candidate.get('confidence', 0.8),
                'method': 'chronology_repair_delivery'
            }

        # Fallback robuste: si certaines dates restent vides, tenter une déduction par année.
        birth_obj = DocumentStrategy._parse_ddmmyyyy(extracted.get('date_naissance', {}).get('value', ''))
        delivery_obj = DocumentStrategy._parse_ddmmyyyy(extracted.get('date_delivrance', {}).get('value', ''))
        expiration_obj = DocumentStrategy._parse_ddmmyyyy(extracted.get('date_expiration', {}).get('value', ''))

        year_candidates = DocumentStrategy._extract_year_candidates(blocks)
        year_candidates = sorted(set(y for y in year_candidates if 2000 <= y <= 2100))

        # 1) Date expiration manquante: prendre l'année future la plus plausible.
        if expiration_obj is None and year_candidates:
            exp_year = None
            future_years = [y for y in year_candidates if y >= current_year]
            if future_years:
                exp_year = max(future_years)
            elif birth_obj:
                after_birth = [y for y in year_candidates if y >= birth_obj.year + 16]
                if after_birth:
                    exp_year = max(after_birth)

            if exp_year is not None:
                extracted['date_expiration'] = {
                    'value': f'01/01/{exp_year}',
                    'confidence': 0.6,
                    'method': 'year_fallback_expiration'
                }
                expiration_obj = datetime(exp_year, 1, 1)

        # 2) Date délivrance manquante: choisir une année <= expiration et > naissance.
        if delivery_obj is None and year_candidates:
            deliv_year = None
            if expiration_obj:
                window = [
                    y for y in year_candidates
                    if y <= expiration_obj.year and (birth_obj is None or y >= birth_obj.year + 16)
                ]
                if window:
                    # Favoriser une date de delivrance proche de expiration-10 ans.
                    target = max(expiration_obj.year - 10, (birth_obj.year + 16) if birth_obj else 2000)
                    deliv_year = min(window, key=lambda y: abs(y - target))
            else:
                plausible = [y for y in year_candidates if (birth_obj is None or y >= birth_obj.year + 16)]
                if plausible:
                    deliv_year = min(plausible)

            if deliv_year is not None:
                extracted['date_delivrance'] = {
                    'value': f'01/01/{deliv_year}',
                    'confidence': 0.55,
                    'method': 'year_fallback_delivery'
                }

        return extracted

    @staticmethod
    def extract(document_type: DocumentType, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Applique l'extraction selon le type de document
        Args:
            blocks: Liste de dicts {id, text, confidence, bbox, label}
        """
        extracted = {}
        if document_type == DocumentType.NINA_CARD:
            extracted = DocumentStrategy._extract_nina(blocks)
        elif document_type == DocumentType.PASSPORT:
            extracted = DocumentStrategy._extract_passport(blocks)
        elif document_type == DocumentType.PASSPORT_BIOMETRIC:
            extracted = DocumentStrategy._extract_passport(blocks)  # Même logique
        elif document_type == DocumentType.ID_CARD:
            extracted = DocumentStrategy._extract_id_card(blocks)
        elif document_type == DocumentType.CIN_BIOMETRIC:
            extracted = DocumentStrategy._extract_id_card(blocks)  # Même logique que CIN
        elif document_type == DocumentType.DRIVER_LICENSE:
            extracted = DocumentStrategy._extract_driver_license(blocks)
        elif document_type == DocumentType.RESIDENCE_PERMIT:
            extracted = DocumentStrategy._extract_residence_permit(blocks)
        elif document_type == DocumentType.VISA:
            extracted = DocumentStrategy._extract_visa(blocks)
        elif document_type == DocumentType.BIRTH_CERTIFICATE:
            extracted = DocumentStrategy._extract_generic(blocks)
        else:
            extracted = DocumentStrategy._extract_generic(blocks)
        return extracted

    # ----------------------------
    # Méthodes spécifiques
    # ----------------------------
    
    @staticmethod
    def _extract_nina(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        extracted = {}
        dates_found = []
        lines = [b["text"] for b in blocks]  # Extraction simple pour NINA
        
        # Termes à filtrer
        # Liste élargie pour filtrer les labels polluants
        excluded_terms = [
            "NINA", "CARTE", "REPUBLIQUE", "MALI", "SENEGAL", "IDENTITE", "CEDEAO", "CCOEA",
            "CARTEDIDENTITECEDEAO", "CARTEDIDENTITE", "CARTENINA", "CARTEDIDENTITECEDEAO", "CARTEDIDENTITE", "CARTENINA", "IVOIRE",
            "CCOEAO", "SCCDEAO", "ECOWAS", "IDENTITY", "SUMARI", "SURNAME"
        ]

        def _is_label_like(value: str) -> bool:
            token = (value or "").upper().strip()
            if not token:
                return True
            token_compact = re.sub(r"[^A-Z0-9]", "", token)
            if token in excluded_terms:
                return True
            for banned in excluded_terms:
                if banned in token:
                    return True
                if banned in token_compact:
                    return True

            # Filtres supplémentaires pour le bruit CEDEAO/OCR.
            if any(k in token_compact for k in ["CEDEAO", "CCOEAO", "ECOWAS", "IDENTITYCARD"]):
                return True
            return False

        def _is_upper_name(value: str) -> bool:
            token = (value or "").upper().strip()
            return bool(re.match(r"^[A-Z][A-Z\-' ]{2,}$", token)) and not _is_label_like(token)

        def _compact(value: str) -> str:
            return re.sub(r"[^A-Z0-9]", "", (value or "").upper())

        def _extract_sex_value(value: str) -> str:
            compact = re.sub(r"[^A-Z]", "", (value or "").upper())
            if compact in {"M", "MALE", "MASCULIN", "MASC"}:
                return "M"
            if compact in {"F", "FEMALE", "FEMININ", "FEMININE", "FEM"}:
                return "F"

            # Fallback CEDEAO quand M/F est absent mais nationalité genrée présente.
            if any(token in compact for token in ["MALIENNE", "GUINEENNE", "IVOIRIENNE", "SENEGALAISE", "BURKINABE"]):
                return "F"
            if any(token in compact for token in ["MALIEN", "GUINEEN", "IVOIRIEN", "SENEGALAIS"]):
                return "M"
            return ""

        # 0) Extraction contextuelle prioritaire autour des labels NOM/PRENOM.
        for i, block in enumerate(blocks):
            label_text = _compact(block.get("text", ""))
            if not label_text:
                continue

            is_nom_label = any(lbl in label_text for lbl in ["NOM", "SURNAME", "SUMAME", "SUMARI", "NOMSUMARI"])
            is_prenom_label = any(lbl in label_text for lbl in ["PRENOM", "FIRSTNAME", "GIVENNAME", "PRENOMFIRSTNAME"])

            if is_nom_label and 'nom' not in extracted:
                for j in range(i + 1, min(i + 4, len(blocks))):
                    candidate = blocks[j]["text"].strip().upper()
                    if _is_upper_name(candidate):
                        extracted['nom'] = {
                            "value": candidate,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break

                # Sur plusieurs CIN CEDEAO, le prenom est juste avant le label NOM.
                if 'prenom' not in extracted and i - 1 >= 0:
                    candidate = blocks[i - 1]["text"].strip().upper()
                    if _is_upper_name(candidate) and candidate != extracted.get('nom', {}).get('value'):
                        extracted['prenom'] = {
                            "value": candidate,
                            "confidence": round(float(blocks[i - 1].get("confidence", 0.0)), 2),
                            "method": "context_before_nom_label"
                        }

            if is_prenom_label and 'prenom' not in extracted:
                for j in range(i + 1, min(i + 4, len(blocks))):
                    candidate = blocks[j]["text"].strip().upper()
                    if _is_upper_name(candidate):
                        extracted['prenom'] = {
                            "value": candidate,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break
        
        # 1) Extraction séquentielle prénom + nom (fallback seulement si manquant).
        if 'prenom' not in extracted or 'nom' not in extracted:
            for i in range(len(lines) - 1):
                prenom_candidate = lines[i].strip().upper()
                nom_candidate = lines[i + 1].strip().upper()

                # Support OCR full-uppercase frequent sur CIN/NINA.
                if _is_upper_name(prenom_candidate) and _is_upper_name(nom_candidate):
                    prenom, nom = (prenom_candidate, nom_candidate) if len(prenom_candidate) >= len(nom_candidate) else (nom_candidate, prenom_candidate)
                    if 'prenom' not in extracted:
                        extracted['prenom'] = {"value": prenom, "confidence": 0.9, "method": "sequential_uppercase"}
                    if 'nom' not in extracted:
                        extracted['nom'] = {"value": nom, "confidence": 0.9, "method": "sequential_uppercase"}
                    if 'prenom' in extracted and 'nom' in extracted:
                        break
        
        # Fallback + autres champs
        for block in blocks:
            line = block["text"].strip()
            
            # NINA: priorité au format avec lettre finale (14-16 chiffres + lettre)
            # Ex: 18306101999099K
            nina_match = re.match(r'^(\d{14,16}[A-Z])$', line)
            if nina_match and 'numero_nina' not in extracted:
                extracted['numero_nina'] = {
                    "value": nina_match.group(1),
                    "confidence": round(block["confidence"], 2),
                    "method": "regex_14-16_letter"
                }
            # NINA: 12 chiffres espacés ou non
            elif re.match(r'^\d{12}$', re.sub(r'\s', '', line)):
                extracted['numero_nina'] = {
                    "value": re.sub(r'\s', '', line),
                    "confidence": round(block["confidence"], 2),
                    "method": "regex_12"
                }
            
            upper_line = line.upper()
            # Fallback prénom : ne pas extraire si label
            if _is_upper_name(upper_line) and 'prenom' not in extracted and not _is_label_like(upper_line):
                extracted['prenom'] = {"value": upper_line, "confidence": 0.7, "method": "fallback_uppercase"}
                continue
            # Fallback nom : ne pas extraire si label
            if _is_upper_name(upper_line) and 'nom' not in extracted and upper_line != extracted.get('prenom', {}).get('value') and not _is_label_like(upper_line):
                extracted['nom'] = {"value": upper_line, "confidence": 0.7, "method": "fallback_uppercase"}
            
            # Dates
            date_match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', line)
            if date_match:
                day, month, year = date_match.groups()
                try:
                    from datetime import datetime
                    date_obj = datetime(int(year), int(month), int(day))
                    dates_found.append({
                        "value": f"{day}/{month}/{year}",
                        "date_obj": date_obj
                    })
                except:
                    pass

            # OCR bruité: DD/MMYYYY (ex: 12/012023)
            noisy_date_match = re.search(r'\b(\d{1,2})[\./-](\d{2})(\d{4})\b', line.replace(" ", ""))
            if noisy_date_match:
                day, month, year = noisy_date_match.groups()
                try:
                    from datetime import datetime
                    date_obj = datetime(int(year), int(month), int(day))
                    dates_found.append({
                        "value": f"{int(day):02d}/{int(month):02d}/{year}",
                        "date_obj": date_obj
                    })
                except:
                    pass

            # Date de delivrance concatenee au label (ex: Delivrele01/05/2015).
            deliv_match = re.search(r'(?:DELIVR|EMIS|EMISSION|ISSU)[A-Z]*\s*(\d{1,2})/(\d{1,2})/(\d{4})', line.upper())
            if deliv_match and 'date_delivrance' not in extracted:
                d, m, y = deliv_match.groups()
                extracted['date_delivrance'] = {
                    "value": f"{int(d):02d}/{int(m):02d}/{y}",
                    "confidence": round(block["confidence"], 2),
                    "method": "context_label_inline"
                }
        
        if dates_found:
            dates_found.sort(key=lambda x: x["date_obj"])
            extracted['date_naissance'] = {"value": dates_found[0]["value"], "confidence": 0.85, "method": "regex_date"}
            
            # Si 3 dates ou plus: date_naissance, date_delivrance, date_expiration
            if len(dates_found) >= 3:
                extracted['date_delivrance'] = {"value": dates_found[1]["value"], "confidence": 0.8, "method": "regex_date"}
                extracted['date_expiration'] = {"value": dates_found[-1]["value"], "confidence": 0.8, "method": "regex_date"}
            elif len(dates_found) >= 2:
                extracted['date_expiration'] = {"value": dates_found[-1]["value"], "confidence": 0.8, "method": "regex_date"}

        # Extraction sexe (labels bruités possibles: Sexe/Ser + nationalité genrée)
        if 'sexe' not in extracted:
            for block in blocks:
                sex_value = _extract_sex_value(block.get("text", ""))
                if sex_value:
                    extracted['sexe'] = {
                        "value": sex_value,
                        "confidence": round(float(block.get("confidence", 0.0)), 2),
                        "method": "fallback_nationality_gender"
                    }
                    break
        
        # Lieu de naissance: chercher label "Lieu de naissance" ou "Lieu" suivi de la ville
        for i, block in enumerate(blocks):
            text = block["text"].strip().upper()
            # Label "LIEU" (de naissance)
            if "LIEU" in text or "NAISSANCE" in text:
                # Si c'est juste le label "Lieu de naissance", chercher le bloc suivant
                if text in ["LIEU", "LIEU DE NAISSANCE", "NAISSANCE"]:
                    if i + 1 < len(blocks):
                        next_text = blocks[i + 1]["text"].strip()
                        # Accepter ville si >= 3 chars, pas un mot-clé, pas une date
                        if (len(next_text) >= 3 and 
                            next_text not in excluded_terms and
                            blocks[i + 1]["confidence"] > 0.8 and
                            not re.match(r'^\d{2}/\d{2}', next_text)):
                            extracted['lieu_naissance'] = {
                                "value": next_text.title(),
                                "confidence": round(blocks[i + 1]["confidence"], 2),
                                "method": "context_label"
                            }
                            break
        
        # ============================================================
        # ÉTAPE FINALE: Assigner intelligemment les dates restantes  
        # ============================================================
        extracted = DocumentStrategy._assign_dates_intelligently(extracted, blocks)
        
        return extracted

    @staticmethod
    def _extract_passport(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extraction passeport avec support MRZ, canadien, moldave et autres formats
        """
        extracted = {}
        
        # Labels (inchangés)
        given_labels = [
            "GIVEN", "PRENUMELE", "GIVEN NAMES", "PRENOM", "PRENOMS", 
            "GIVEN NAME", "FIRST NAME", "PRÉNOM", "PRÉNOMS"
        ]
        surname_labels = [
            "SURNAME", "NOM", "NUMELE", "SURNOM", "LAST NAME",
            "FAMILY NAME", "SURNAME(S)", "NOM(S)"
        ]
        passport_labels = [
            "PASSPORT", "PASSEPORT", "PASAPORT", "PASSPORT NO", "N° PASSEPORT",
            "PASSPORT NUMBER", "PASSEPORT N°", "PASSPORT NO."
        ]
        birth_labels = [
            "DATE OF BIRTH", "DATE DE NAISSANCE", "BIRTH DATE", "DOB",
            "DATA NASTERII", "DATE NAISSANCE", "NAISSANCE"
        ]
        expiry_labels = [
            "DATE OF EXPIRY", "DATE D'EXPIRATION", "EXPIRY DATE",
            "DATE EXPIRATION", "EXPIRATION", "EXPIRE"
        ]
        issuance_labels = [
            "DATE OF ISSUE", "DATE D'EMISSION", "DATE EMISSION", "ISSUED",
            "DATE DELIVERED", "DATE OF DELIVERY", "DATE DELIVRANCE",
            "DATE ISSUED", "ÉMISSION", "DELIVERY"
        ]
        place_labels = [
            "PLACE OF BIRTH", "LIEU DE NAISSANCE", "BIRTH PLACE",
            "LOCUL NASTERII", "LIEU NAISSANCE"
        ]
        
        excluded_terms = [
            "PASSEPORT", "PASSPORT", "PASAPORT", "PASSAPORTU",
            "REPUBLIQUE", "REPUBLIC", "REPUBLICA", "MOLDOVA", "MOLDOVEI",
            "CANADA", "CANADIAN", "CANADIENNE",
            "BIOMETRIC", "BIOMETRIQUE", "TYPE", "CODE",
            "NATIONALITY", "NATIONALITE", "DATE", "PLACE",
            "SEXE", "SEX", "F", "M", "MF", "M/F",
            "AUTORITE", "AUTHORITY", "ISSUING", "ISSUE",
            "SIGNATURE", "SIGNATURA", "HOLDER", "TITULAIRE",
            "PP", "CAN", "OIAUC", "66", "siver", "enom", "06"
        ]

        # Marqueurs non nominaux observés dans les zones signalétiques.
        non_name_markers = {
            "YEUX", "NOIR", "NOIRS", "TAILLE", "HEIGHT", "SIGNES", "PARTICULIERS",
            "DOMICILE", "ADDRESS", "HOLDER", "SIGNATURE", "TITULAIRE", "GUINEENNE", "GUINEEN"
        }
        forbidden_name_tokens = set(t.upper() for t in excluded_terms) | non_name_markers
        
        used_blocks = set()
        high_conf_blocks = [b for b in blocks if b["confidence"] > 0.9]
        
        # ============================================================
        # 1. DÉTECTION MRZ (prioritaire pour passeports avec bande MRZ)
        # ============================================================
        mrz_lines = MRZParser.find_mrz_blocks(blocks)
        if mrz_lines:
            mrz_data = MRZParser.parse_td3(mrz_lines[0], mrz_lines[1])
            if mrz_data:
                extracted.update(mrz_data)

                # Sanity check: rejeter immédiatement les noms/prénoms MRZ aberrants.
                for name_field in ("nom", "prenom"):
                    if name_field in extracted:
                        name_value = str(extracted[name_field].get("value", ""))
                        if not DocumentStrategy._is_plausible_person_name(name_value, forbidden_name_tokens):
                            extracted.pop(name_field, None)

                # Ajouter dynamiquement les codes pays MRZ aux termes exclus des noms.
                for code_key in ("code_pays", "code_pays_emetteur"):
                    code_val = mrz_data.get(code_key, {}).get("value") if isinstance(mrz_data.get(code_key), dict) else None
                    if isinstance(code_val, str) and re.match(r'^[A-Z]{3}$', code_val):
                        excluded_terms.append(code_val)
                
                # Nettoyer le prénom MRZ si nécessaire (cas moldave)
                if 'prenom' in extracted and len(extracted['prenom']['value']) >= 7:
                    prenom_mrz = extracted['prenom']['value']
                    # Chercher un prénom plus plausible dans les blocs haute confiance
                    for block in high_conf_blocks:
                        if block["id"] in used_blocks:
                            continue
                        text = block["text"].strip()
                        if (re.match(r'^[A-Z]{4,8}$', text) and
                            block["confidence"] > 0.95 and
                            text not in excluded_terms and
                            text != extracted.get('nom', {}).get('value')):
                            
                            # Vérifier si ce texte pourrait être le vrai prénom
                            if (text in prenom_mrz or 
                                any(text in part for part in prenom_mrz.replace('<', ' ').split())):
                                extracted['prenom'] = {
                                    "value": text,
                                    "confidence": round(block["confidence"], 2),
                                    "method": "mrz_corrected"
                                }
                                used_blocks.add(block["id"])
                                break

                    # Correction spécifique des artefacts OCR MRZ (ex: TATIANAZ -> TATIANA)
                    if extracted.get('prenom', {}).get('value', '').endswith('Z'):
                        base_name = extracted['prenom']['value'][:-1]
                        for block in high_conf_blocks:
                            if block["id"] in used_blocks:
                                continue
                            candidate = block["text"].strip().upper()
                            if (
                                candidate == base_name
                                and re.match(r'^[A-Z]{3,}$', candidate)
                                and candidate not in excluded_terms
                            ):
                                extracted['prenom'] = {
                                    "value": candidate,
                                    "confidence": round(block["confidence"], 2),
                                    "method": "mrz_corrected_trailing_char"
                                }
                                used_blocks.add(block["id"])
                                break
                
                # Ne pas retourner trop tôt: la date de délivrance n'est pas dans la MRZ
                # et doit être recherchée dans les autres blocs OCR.
        
        # ============================================================
        # 2. EXTRAIRE LE NUMÉRO DE PASSEPORT
        # ============================================================
        if 'numero_passeport' not in extracted:
            for block in sorted(blocks, key=lambda b: b.get("confidence", 0), reverse=True):
                text = block["text"].upper()

                # Format MRZ compact TD3 generique (sans '<' visibles)
                # Exemple: P13756AA0CAN9008010F3301144
                # Structure: [doc_number][check][country][dob][check][sex][expiry]
                mrz_compact_match = re.search(r'\b([A-Z0-9]{6,9})(\d)([A-Z]{3})(\d{6})(\d)([MF<])(\d{6})', text)
                if mrz_compact_match:
                    doc_number_raw = mrz_compact_match.group(1)
                    doc_number = re.sub(r'[^A-Z0-9]', '', doc_number_raw).replace('<', '')
                    if 6 <= len(doc_number) <= 9:
                        extracted['numero_passeport'] = {
                            "value": doc_number,
                            "confidence": round(block["confidence"], 2),
                            "method": "mrz_compact"
                        }

                        # Bonus: code pays/nationalite si absents
                        country_code = mrz_compact_match.group(3)
                        if 'code_pays' not in extracted:
                            extracted['code_pays'] = {
                                "value": country_code,
                                "confidence": round(block["confidence"], 2),
                                "method": "mrz_compact"
                            }
                        if 'nationalite' not in extracted:
                            extracted['nationalite'] = {
                                "value": country_code,
                                "confidence": round(block["confidence"], 2),
                                "method": "mrz_compact"
                            }

                        # Bonus: sexe si absent
                        if 'sexe' not in extracted and mrz_compact_match.group(6) in ['M', 'F']:
                            extracted['sexe'] = {
                                "value": mrz_compact_match.group(6),
                                "confidence": round(block["confidence"], 2),
                                "method": "mrz_compact"
                            }

                        used_blocks.add(block["id"])
                        break
                
                # Format alphanumerique usuel: 1 lettre + 5-7 chiffres + 2 lettres
                canadian_match = re.search(r'\b([A-Z]\d{5,7}[A-Z]{2})\b', text)
                if canadian_match:
                    extracted['numero_passeport'] = {
                        "value": canadian_match.group(1),
                        "confidence": round(block["confidence"], 2),
                        "method": "canadian_format"
                    }
                    used_blocks.add(block["id"])
                    break
                
                # Format moldave: AP0000000 (2 lettres + 7 chiffres)
                moldovan_match = re.search(r'\b([A-Z]{2}\d{7})\b', text)
                if moldovan_match:
                    extracted['numero_passeport'] = {
                        "value": moldovan_match.group(1),
                        "confidence": round(block["confidence"], 2),
                        "method": "moldovan_format"
                    }
                    used_blocks.add(block["id"])
                    break

                # Format MRZ concaténé: AP00000005MDA... -> capturer AP0000000
                mrz_concat_match = re.search(r'([A-Z]{2}\d{7})\d[A-Z]{3}', text)
                if mrz_concat_match:
                    extracted['numero_passeport'] = {
                        "value": mrz_concat_match.group(1),
                        "confidence": round(block["confidence"], 2),
                        "method": "mrz_concat_prefix"
                    }
                    used_blocks.add(block["id"])
                    break
                
                # Format standard: 1-2 lettres + 6-9 chiffres
                standard_match = re.search(r'\b([A-Z]{1,2}\d{6,9})\b', text)
                if standard_match:
                    numero = standard_match.group(1)
                    if numero not in excluded_terms:
                        extracted['numero_passeport'] = {
                            "value": numero,
                            "confidence": round(block["confidence"], 2),
                            "method": "regex_alphanum"
                        }
                        used_blocks.add(block["id"])
                        break
                
                # Format dans une longue chaîne (ex: P123456AA0CAN...)
                embedded_match = re.search(r'([A-Z]\d{6,7}[A-Z]{2})', text)
                if embedded_match and 'numero_passeport' not in extracted:
                    extracted['numero_passeport'] = {
                        "value": embedded_match.group(1),
                        "confidence": round(block["confidence"], 2),
                        "method": "embedded_format"
                    }
                    used_blocks.add(block["id"])
                    break

        # Fallback nationalite: reutiliser code_pays/code_pays_emetteur si nationalite absente
        if 'nationalite' not in extracted:
            for code_key in ('code_pays', 'code_pays_emetteur'):
                code_data = extracted.get(code_key)
                if isinstance(code_data, dict):
                    code_val = str(code_data.get('value', '')).strip().upper()
                    if re.match(r'^[A-Z]{3}$', code_val):
                        extracted['nationalite'] = {
                            "value": code_val,
                            "confidence": code_data.get('confidence', 0.9),
                            "method": "derived_country_code"
                        }
                        break
        
        # ============================================================
        # 3. EXTRAIRE LE NOM (SURNAME)
        # ============================================================
        if 'nom' not in extracted:
            for i, block in enumerate(blocks):
                if block["id"] in used_blocks:
                    continue
                text = block["text"].upper()
                if any(DocumentStrategy._text_has_label(text, label) for label in surname_labels):
                    # Chercher dans les 2 blocs suivants
                    for j in range(i + 1, min(i + 3, len(blocks))):
                        if blocks[j]["id"] in used_blocks:
                            continue
                        candidate = blocks[j]["text"].upper().strip()
                        if (blocks[j]["confidence"] > 0.85 and
                            re.match(r'^[A-Z]{2,}$', candidate) and
                            candidate not in excluded_terms and
                            DocumentStrategy._is_plausible_person_name(candidate, forbidden_name_tokens)):
                            extracted['nom'] = {
                                "value": candidate,
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break
                    if 'nom' in extracted:
                        break
        
        # ============================================================
        # 4. EXTRAIRE LE PRÉNOM (GIVEN NAME)
        # ============================================================
        # Heuristique générique: si nom+prénom absents, utiliser une paire de blocs
        # adjacents (souvent NOM puis PRENOM sur passeports), pour éviter que
        # direct_match prenne le NOM comme PRENOM.
        if 'nom' not in extracted and 'prenom' not in extracted:
            name_candidates = []
            for block in blocks:
                txt = block["text"].strip().upper()
                if (
                    block.get("confidence", 0) >= 0.9
                    and re.match(r'^[A-Z]{3,20}$', txt)
                    and txt not in excluded_terms
                    and DocumentStrategy._is_plausible_person_name(txt, forbidden_name_tokens)
                ):
                    bbox = block.get("bbox") or []
                    if bbox and len(bbox) >= 4:
                        y = bbox[0][1]
                        x = bbox[0][0]
                    else:
                        y = 10**9
                        x = 10**9
                    name_candidates.append((y, x, block))

            name_candidates.sort(key=lambda item: (item[0], item[1]))

            for i in range(len(name_candidates) - 1):
                y1, x1, b1 = name_candidates[i]
                y2, x2, b2 = name_candidates[i + 1]

                # Blocs proches verticalement avec ordre de lecture naturel.
                if y2 >= y1 and abs(y2 - y1) <= 90:
                    nom_candidate = b1["text"].strip().upper()
                    prenom_candidate = b2["text"].strip().upper()

                    if nom_candidate != prenom_candidate:
                        extracted['nom'] = {
                            "value": nom_candidate,
                            "confidence": round(b1.get("confidence", 0), 2),
                            "method": "adjacent_name_pair"
                        }
                        extracted['prenom'] = {
                            "value": prenom_candidate,
                            "confidence": round(b2.get("confidence", 0), 2),
                            "method": "adjacent_name_pair"
                        }
                        used_blocks.add(b1["id"])
                        used_blocks.add(b2["id"])
                        break

        if 'prenom' not in extracted:
            # Méthode 1: Chercher après le label "Given names"
            for i, block in enumerate(blocks):
                if block["id"] in used_blocks:
                    continue
                text = block["text"].upper()
                if any(DocumentStrategy._text_has_label(text, label) for label in given_labels):
                    for j in range(i + 1, min(i + 4, len(blocks))):
                        if blocks[j]["id"] in used_blocks:
                            continue
                        candidate = blocks[j]["text"].strip()
                        if (re.match(r'^[A-Z]{3,8}$', candidate) and
                            blocks[j]["confidence"] > 0.85 and
                            candidate not in excluded_terms and
                            DocumentStrategy._is_plausible_person_name(candidate, forbidden_name_tokens) and
                            candidate != extracted.get('nom', {}).get('value')):
                            extracted['prenom'] = {
                                "value": candidate,
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break
                    if 'prenom' in extracted:
                        break
            
            # Méthode 2: Si nom trouvé, chercher le bloc suivant (position)
            if 'prenom' not in extracted and 'nom' in extracted:
                nom_value = extracted['nom']['value']
                nom_block_id = None
                
                # Trouver le bloc du nom
                for block in blocks:
                    if block["text"].strip().upper() == nom_value:
                        nom_block_id = block["id"]
                        break
                
                if nom_block_id:
                    for i, block in enumerate(blocks):
                        if block["id"] == nom_block_id:
                            # Regarder les 2-3 blocs suivants
                            for j in range(i + 1, min(i + 4, len(blocks))):
                                if blocks[j]["id"] in used_blocks:
                                    continue
                                candidate = blocks[j]["text"].strip()
                                if (re.match(r'^[A-Z]{3,8}$', candidate) and
                                    blocks[j]["confidence"] > 0.9 and
                                    candidate not in excluded_terms and
                                    DocumentStrategy._is_plausible_person_name(candidate, forbidden_name_tokens) and
                                    candidate != nom_value):
                                    extracted['prenom'] = {
                                        "value": candidate,
                                        "confidence": round(blocks[j]["confidence"], 2),
                                        "method": "position_after_name"
                                    }
                                    used_blocks.add(blocks[j]["id"])
                                    break
                            break
            
            # Méthode 3: Recherche directe dans les blocs haute confiance
            if 'prenom' not in extracted:
                for block in high_conf_blocks:
                    if block["id"] in used_blocks:
                        continue
                    text = block["text"].strip()
                    if (re.match(r'^[A-Z]{4,20}$', text) and
                        block["confidence"] > 0.95 and
                        text not in excluded_terms and
                        DocumentStrategy._is_plausible_person_name(text, forbidden_name_tokens) and
                        text != extracted.get('nom', {}).get('value')):
                        
                        if text not in ['CANADA', 'MOLDOVA', 'PASSPORT', 'PASSEPORT']:
                            extracted['prenom'] = {
                                "value": text,
                                "confidence": round(block["confidence"], 2),
                                "method": "direct_match"
                            }
                            used_blocks.add(block["id"])
                            break
        
        # ============================================================
        # 5. EXTRAIRE LA DATE DE NAISSANCE
        # ============================================================
        if 'date_naissance' not in extracted:
            # Chercher le format DDMMYYYY
            for block in sorted(blocks, key=lambda b: b.get("confidence", 0), reverse=True):
                if block["id"] in used_blocks:
                    continue
                text = block["text"].strip()
                if re.match(r'^\d{8}$', text):
                    try:
                        day, month, year = text[:2], text[2:4], text[4:]
                        year_int = int(year)
                        if year_int > datetime.utcnow().year:
                            continue
                        datetime(year_int, int(month), int(day))
                        extracted['date_naissance'] = {
                            "value": f"{day}/{month}/{year}",
                            "confidence": round(block["confidence"], 2),
                            "method": "compact_date"
                        }
                        used_blocks.add(block["id"])
                        break
                    except:
                        pass
            
            # Chercher dans les labels de date de naissance
            if 'date_naissance' not in extracted:
                for i, block in enumerate(blocks):
                    if block["id"] in used_blocks:
                        continue
                    text = block["text"].upper()
                    if any(DocumentStrategy._text_has_label(text, label) for label in birth_labels):
                        for j in range(i + 1, min(i + 4, len(blocks))):
                            if blocks[j]["id"] in used_blocks:
                                continue
                            date_text = blocks[j]["text"].upper().replace('O', '0')
                            # Format D1AUG/A0UTE1990
                            date_match = re.search(r'(\d{1,2})([A-Z]{3})/(?:[A-Z]{3,})(\d{4})', date_text)
                            if date_match:
                                day, month_abbr, year = date_match.groups()
                                months = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                                        'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                                        'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
                                month_num = months.get(month_abbr, '01')
                                extracted['date_naissance'] = {
                                    "value": f"{int(day):02d}/{month_num}/{year}",
                                    "confidence": round(blocks[j]["confidence"], 2),
                                    "method": "context_label"
                                }
                                used_blocks.add(blocks[j]["id"])
                                break
        
        # ============================================================
        # 6. EXTRAIRE LA DATE D'EXPIRATION
        # ============================================================
        if 'date_expiration' not in extracted:
            for i, block in enumerate(blocks):
                if block["id"] in used_blocks:
                    continue
                text = block["text"].upper()
                if any(DocumentStrategy._text_has_label(text, label) for label in expiry_labels):
                    for j in range(i + 1, min(i + 4, len(blocks))):
                        if blocks[j]["id"] in used_blocks:
                            continue
                        date_text = blocks[j]["text"].upper().replace('O', '0')
                        # Format 14JAN/JAN2033
                        date_match = re.search(r'(\d{1,2})([A-Z]{3})/(?:[A-Z]{3,})(\d{4})', date_text)
                        if date_match:
                            day, month_abbr, year = date_match.groups()
                            months = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                                    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                                    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
                            month_num = months.get(month_abbr, '01')
                            extracted['date_expiration'] = {
                                "value": f"{int(day):02d}/{month_num}/{year}",
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break

                        # Format MMYYYY ou MM/YYYY (ex: 042033)
                        compact_match = re.search(r'\b(0[1-9]|1[0-2])\s*/?\s*((?:19|20)\d{2})\b', date_text)
                        if compact_match:
                            month, year = compact_match.groups()
                            extracted['date_expiration'] = {
                                "value": f"01/{month}/{year}",
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label_month_year"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break
            
            # Si pas trouvé par label, chercher des dates dans les blocs
            if 'date_expiration' not in extracted:
                for block in sorted(blocks, key=lambda b: b.get("confidence", 0), reverse=True):
                    if block["id"] in used_blocks:
                        continue
                    text = block["text"].upper().replace('O', '0')
                    # Format 14JAN/JAN2033 sans label
                    date_match = re.search(r'(\d{1,2})([A-Z]{3})/(?:[A-Z]{3,})(\d{4})', text)
                    if date_match:
                        day, month_abbr, year = date_match.groups()
                        months = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                                'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                                'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
                        month_num = months.get(month_abbr, '01')
                        extracted['date_expiration'] = {
                            "value": f"{int(day):02d}/{month_num}/{year}",
                            "confidence": round(block["confidence"], 2),
                            "method": "regex_date"
                        }
                        used_blocks.add(block["id"])
                        break
        
        # ============================================================
        # 7. EXTRAIRE LA DATE DE DELIVRANCE / EMISSION
        # ============================================================
        if 'date_delivrance' not in extracted:
            for i, block in enumerate(blocks):
                if block["id"] in used_blocks:
                    continue
                text = block["text"].upper()
                if (
                    any(DocumentStrategy._text_has_label(text, label) for label in issuance_labels)
                    or (
                        ("DATE" in text or "DOTE" in text)
                        and re.search(r'(ISSUE|LSSUE|EMISSION|DELIVR|DELIVERY)', text)
                    )
                ):
                    for j in range(i + 1, min(i + 4, len(blocks))):
                        if blocks[j]["id"] in used_blocks:
                            continue
                        date_text = blocks[j]["text"].upper().replace('O', '0')
                        # Format 14JAN/JAN2033
                        date_match = re.search(r'(\d{1,2})([A-Z]{3})/(?:[A-Z]{3,})(\d{4})', date_text)
                        if date_match:
                            day, month_abbr, year = date_match.groups()
                            months = {'JAN': '01', 'FEB': '02', 'MAR': '03', 'APR': '04',
                                    'MAY': '05', 'JUN': '06', 'JUL': '07', 'AUG': '08',
                                    'SEP': '09', 'OCT': '10', 'NOV': '11', 'DEC': '12'}
                            month_num = months.get(month_abbr, '01')
                            extracted['date_delivrance'] = {
                                "value": f"{int(day):02d}/{month_num}/{year}",
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break

                        # Format MMYYYY ou MM/YYYY (ex: 042023)
                        compact_match = re.search(r'\b(0[1-9]|1[0-2])\s*/?\s*((?:19|20)\d{2})\b', date_text)
                        if compact_match:
                            month, year = compact_match.groups()
                            extracted['date_delivrance'] = {
                                "value": f"01/{month}/{year}",
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label_month_year"
                            }
                            used_blocks.add(blocks[j]["id"])
                            break
            
            # FALLBACK: Si pas trouvé par label, chercher des dates DD/MM/YYYY dans les blocs
            if 'date_delivrance' not in extracted:
                for block in sorted(blocks, key=lambda b: b.get("confidence", 0), reverse=True):
                    if block["id"] in used_blocks:
                        continue
                    text = block["text"]
                    # Chercher format DD/MM/YYYY (mais éviter d'utiliser date_expiration si déjà trouvée)
                    date_match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', text)
                    if date_match:
                        day, month, year = date_match.groups()
                        try:
                            from datetime import datetime
                            # Valider la date
                            datetime(int(year), int(month), int(day))
                            extracted['date_delivrance'] = {
                                "value": f"{day}/{month}/{year}",
                                "confidence": round(block["confidence"], 2),
                                "method": "regex_date"
                            }
                            used_blocks.add(block["id"])
                            break
                        except ValueError:
                            pass
        
        # ============================================================
        # 8. ÉTAPE FINALE: Assigner intelligemment les dates restantes
        # ============================================================
        extracted = DocumentStrategy._assign_dates_intelligently(extracted, blocks)

        # Fallback de cohérence passeport: si expiration connue mais délivrance absente,
        # déduire une délivrance probable 10 ans avant expiration.
        exp_data = extracted.get('date_expiration', {}) if isinstance(extracted.get('date_expiration'), dict) else {}
        deliv_data = extracted.get('date_delivrance', {}) if isinstance(extracted.get('date_delivrance'), dict) else {}
        birth_data = extracted.get('date_naissance', {}) if isinstance(extracted.get('date_naissance'), dict) else {}

        exp_value = exp_data.get('value', '').strip()
        deliv_value = deliv_data.get('value', '').strip()
        birth_value = birth_data.get('value', '').strip()

        if exp_value and not deliv_value:
            exp_dt = DocumentStrategy._parse_ddmmyyyy(exp_value)
            birth_dt = DocumentStrategy._parse_ddmmyyyy(birth_value) if birth_value else None
            if exp_dt:
                try:
                    inferred_deliv = exp_dt.replace(year=exp_dt.year - 10)
                except ValueError:
                    # Gestion 29/02 en année non bissextile
                    inferred_deliv = exp_dt.replace(year=exp_dt.year - 10, day=28)

                if not birth_dt or inferred_deliv.year >= birth_dt.year + 16:
                    extracted['date_delivrance'] = {
                        "value": inferred_deliv.strftime('%d/%m/%Y'),
                        "confidence": 0.7,
                        "method": "derived_from_expiration"
                    }

        # Nettoyage final anti-bruit OCR/MRZ pour nom/prénom.
        for name_field in ("nom", "prenom"):
            if name_field in extracted:
                name_value = str(extracted[name_field].get("value", ""))
                if not DocumentStrategy._is_plausible_person_name(name_value, forbidden_name_tokens):
                    extracted.pop(name_field, None)
        
        return extracted

    @staticmethod
    def _extract_id_card(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extraction CIN/ID_CARD : détecte format NINA, US ID, ou extraction générique CIN
        """
        # Vérifier si c'est une carte NINA (numéro 14-16 chiffres + lettre)
        for block in blocks:
            text = block["text"].strip()
            nina_match = re.match(r'^(\d{14,16}[A-Z])$', text)
            if nina_match:
                # C'est une NINA, utiliser l'extraction NINA
                nina_data = DocumentStrategy._extract_nina(blocks)
                # Renommer numero_nina → numero_id pour compatibilité ID_CARD
                if 'numero_nina' in nina_data:
                    nina_data['numero_id'] = nina_data.pop('numero_nina')
                return DocumentStrategy._annotate_cin_locations(nina_data, blocks)
        
        # Vérifier si c'est une carte US/NYC ID.
        # Important: éviter les faux positifs sur cartes CEDEAO qui contiennent "IDENTITY CARD".
        full_text = " ".join([b["text"] for b in blocks]).upper()
        us_hard_markers = ["NYC", "IDNYC", "NEW YORK"]
        us_soft_markers = ["US ID", "USA", "ID NUMBER", "DOB", "ISSUANCE DATE", "EXPIRATION DATE"]
        us_soft_hits = sum(1 for marker in us_soft_markers if marker in full_text)

        if any(marker in full_text for marker in us_hard_markers) or us_soft_hits >= 2:
            us_data = DocumentStrategy._extract_us_id_card(blocks)
            if us_data:
                return us_data
        
        # Sinon extraction générique CIN classique
        generic = DocumentStrategy._extract_generic(blocks)

        # Compatibilité ID_CARD: promouvoir numero_principal vers numero_id si nécessaire.
        if 'numero_id' not in generic and isinstance(generic.get('numero_principal'), dict):
            number_data = generic.get('numero_principal', {})
            number_value = str(number_data.get('value', '')).strip()
            if number_value:
                generic['numero_id'] = {
                    "value": number_value,
                    "confidence": number_data.get('confidence', 0.75),
                    "method": "derived_numero_principal"
                }

        return DocumentStrategy._annotate_cin_locations(generic, blocks)


    @staticmethod
    def _extract_us_id_card(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extraction spécifique pour cartes US/NYC ID avec contexte labels
        IMPORTANT: Dates au format MM/DD/YYYY (américain), pas DD/MM/YYYY
        Gère: ID NUMBER, NAME (surname + given), DOB, expiration dates
        Recherche jusqu'à 5 blocs après chaque label pour gérer les espacements OCR
        """
        extracted = {}
        
        excluded_terms = [
            "NYC", "IDENTIFICATION", "CARD", "IDENTIFICATION CARD", 
            "ORGAN", "DONOR", "ORGAN DONOR", "US", "ID", "NEW YORK",
            "ISSUANCE", "EXPIRATION", "ISSUE", "EXPIRE", "ADDRESS",
            "EYE", "COLOR", "HEIGHT", "GENDER", "BIRTH", "DATE", "SUANCEDATE"
        ]
        
        # Extraction avec contexte: chercher labels et récupérer blocs suivants
        for i, block in enumerate(blocks):
            text = block["text"].strip().upper()
            
            # 1. ID NUMBER : format "#### ###### ####" ou fragmenté
            if "ID" in text and "NUMBER" in text:
                # Chercher dans les 2 blocs suivants
                for j in range(i + 1, min(i + 3, len(blocks))):
                    next_text = blocks[j]["text"].strip()
                    # Format US: 4 ou 3 espacements de chiffres (peut être "1234 5678901234" OCR error)
                    id_match = re.search(r'(\d{4})\s*(\d{6,7})\s*(\d{4})', next_text)
                    if id_match and 'numero_id' not in extracted:
                        numero = f"{id_match.group(1)} {id_match.group(2)} {id_match.group(3)}"
                        extracted['numero_id'] = {
                            "value": numero,
                            "confidence": round(blocks[j]["confidence"], 2),
                            "method": "context_label"
                        }
                        break
            
            # 2. NAME : bloc suivant = Surname (NOM), bloc +2 = Given Name (PRENOM)
            elif text == "NAME":
                if i + 1 < len(blocks):
                    surname_block = blocks[i + 1]
                    surname_text = surname_block["text"].strip()
                    # Le bloc après NAME est le surname (NOM)
                    if surname_text and surname_text not in excluded_terms and re.match(r'^[A-Z]{2,}', surname_text):
                        extracted['nom'] = {
                            "value": surname_text.upper(),
                            "confidence": round(surname_block["confidence"], 2),
                            "method": "context_label"
                        }
                
                if i + 2 < len(blocks):
                    given_block = blocks[i + 2]
                    given_text = given_block["text"].strip()
                    # Format: "PRENOM, X" ou "PRENOM" - extraire le prénom avant la virgule/espace
                    first_name = given_text.split(',')[0].split()[0].strip()
                    if first_name and len(first_name) > 1 and first_name not in excluded_terms:
                        extracted['prenom'] = {
                            "value": first_name.title(),
                            "confidence": round(given_block["confidence"], 2),
                            "method": "context_label"
                        }
            
            # 3. DATE OF BIRTH (ou DOB, ou OCR error "DATE.OEBIRT", "DATE.OEBIRTH")
            # Format US: MM/DD/YYYY (américain, pas DD/MM/YYYY!)
            elif "BIRTH" in text or "OEBIRT" in text or "OEBIRTH" in text or "DOB" in text:
                # Chercher date jusqu'à 5 blocs après
                for j in range(i, min(i + 6, len(blocks))):
                    date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', blocks[j]["text"])
                    if date_match and 'date_naissance' not in extracted:
                        month, day, year = date_match.groups()  # Format US: MM/DD/YYYY
                        try:
                            from datetime import datetime
                            datetime(int(year), int(month), int(day))  # Validate
                            extracted['date_naissance'] = {
                                "value": f"{day}/{month}/{year}",  # Retourner DD/MM/YYYY
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            break
                        except:
                            pass
            
            # 4. EXPIRATION DATE
            elif "EXPIRATION" in text and "DATE" in text:
                # Chercher date jusqu'à 3 blocs après
                for j in range(i + 1, min(i + 4, len(blocks))):
                    date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', blocks[j]["text"])
                    if date_match and 'date_expiration' not in extracted:
                        month, day, year = date_match.groups()  # Format US: MM/DD/YYYY
                        try:
                            from datetime import datetime
                            datetime(int(year), int(month), int(day))  # Validate
                            extracted['date_expiration'] = {
                                "value": f"{day}/{month}/{year}",  # Retourner DD/MM/YYYY
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            break
                        except:
                            pass
            
            # 5. ISSUANCE DATE / DATE OF ISSUE
            # Les variantes OCR courantes: ISSUANCE, ISSUE, SUANCE (OCR error), ISANCE
            elif re.search(r'(ISSUANCE|ISSUE|SUANCE|ISANCE)', text) and "DATE" in text and "EXPIRATION" not in text:
                # Chercher date jusqu'à 3 blocs après
                for j in range(i + 1, min(i + 4, len(blocks))):
                    date_match = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', blocks[j]["text"])
                    if date_match and 'date_delivrance' not in extracted:
                        month, day, year = date_match.groups()  # Format US: MM/DD/YYYY
                        try:
                            from datetime import datetime
                            datetime(int(year), int(month), int(day))  # Validate
                            extracted['date_delivrance'] = {
                                "value": f"{day}/{month}/{year}",  # Retourner DD/MM/YYYY
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            break
                        except:
                            pass
            
            # 6. PLACE OF BIRTH (lieu de naissance)
            # Pas toujours présent sur cartes d'identité US, mais certaines l'ont
            elif "PLACE" in text and "BIRTH" in text:
                # Chercher jusqu'à 3 blocs après
                for j in range(i + 1, min(i + 4, len(blocks))):
                    candidate = blocks[j]["text"].strip()
                    # Ville/État format (ex: "Brooklyn, NY")
                    if (len(candidate) >= 3 and 
                        candidate not in excluded_terms and
                        blocks[j]["confidence"] > 0.85 and
                        not re.search(r'\d{1,2}/\d{1,2}/\d{4}', candidate)):
                        extracted['lieu_naissance'] = {
                            "value": candidate.title(),
                            "confidence": round(blocks[j]["confidence"], 2),
                            "method": "context_label"
                        }
                        break
        
        # ============================================================
        # ÉTAPE FINALE: Assigner intelligemment les dates restantes
        # ============================================================
        # Utiliser la logique chronologique pour les dates non détectées
        extracted = DocumentStrategy._assign_dates_intelligently(extracted, blocks)
        
        return extracted if extracted else None

    @staticmethod
    def _extract_driver_license(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return DocumentStrategy._extract_generic(blocks)

    @staticmethod
    def _extract_residence_permit(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return DocumentStrategy._extract_generic(blocks)

    @staticmethod
    def _extract_visa(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return DocumentStrategy._extract_generic(blocks)

    @staticmethod
    def _extract_generic(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Extraction générique AMÉLIORÉE avec séquence et dates triées
        """
        extracted = {}
        dates_found = []
        lines = [b["text"] for b in blocks]  # Conversion simple pour générique
        excluded_terms = {
            "REPUBLIQUE", "MALI", "SENEGAL", "COTE", "IVOIRE", "CARTE", "IDENTITE", "CEDEAO",
            "PASSPORT", "PASSEPORT", "NINA", "DATE", "NAISSANCE", "EXPIRATION", "DELIVRANCE",
            "NATIONALITE", "SEXE", "SEX", "MALIENNE", "MALIEN", "RUOF",
            "GUINEE", "GUINEENNE", "GUINEEN", "ECOWAS", "IDENTITY", "CARD",
            "CONAKRY", "CODEPAYS", "TEINT", "CHEVEUX", "LIEUDEDELIVRANCE", "LIEUNAISSANCE"
        }

        surname_labels = [
            "NOM", "SURNAME", "SUMAME", "LASTNAME", "FAMILYNAME", "NOMS"
        ]
        given_labels = [
            "PRENOM", "PRENOMS", "PREHOM", "FIRSTNAME", "FIRSTNEN", "GIVENNAME", "GIVENNAMES"
        ]
        id_labels = [
            "NUMEROIDENTITE", "IDNUMBER", "IDENTITYNUMBER", "NUMERODIDENTITE", "NUMBER"
        ]

        def normalize_label_text(value: str) -> str:
            if not isinstance(value, str):
                return ""
            return re.sub(r"[^A-Z0-9]", "", value.upper())

        def is_label_like(word: str) -> bool:
            upper = (word or "").upper().strip()
            if not upper:
                return True
            if any(token in upper for token in [
                "IDENTITE", "CARTE", "REPUBLIQUE", "CEDEAO", "PASSPORT",
                "DATE", "BIRTH", "NAISSANCE", "EXPIR", "DELIVR", "ISSU",
                "TAILLE", "HEIGHT", "PLACE", "LIEU", "SEXE", "SEX", "NATIONAL",
                "CONAKRY", "CODEPAYS", "TEINT", "CHEVEUX"
            ]):
                return True
            # Labels OCR fusionnés fréquents: NOMDSUMAI, PRENOMFIRSTNAME, etc.
            compact = re.sub(r"[^A-Z0-9]", "", upper)
            if (
                compact.startswith("NOM")
                or compact.startswith("PRENOM")
                or "FIRSTNAME" in compact
                or "FIRSTNEN" in compact
                or "GIVENNAME" in compact
                or "SURNAME" in compact
                or "SUMAME" in compact
                or "SUMARI" in compact
                or "SUMAI" in compact
                or "PREHOM" in compact
                or "NUMERODIDENTITE" in compact
                or compact.startswith("REPUBL")
                or compact.startswith("REPUBLIC")
            ):
                return True
            return upper in excluded_terms

        def is_name_candidate(word: str) -> bool:
            upper = (word or "").upper().strip()
            if len(upper) < 3 or len(upper) > 30:
                return False
            if not re.match(r'^[A-Z][A-Z\-\' ]+$', upper):
                return False
            if re.search(r'\d', upper):
                return False
            if any(fragment in re.sub(r"[^A-Z]", "", upper) for fragment in [
                "NOM", "PRENOM", "PREHOM", "FIRSTNEN", "FIRSTNAME",
                "SUMAME", "SUMARI", "SUMAI", "NATIONALITE", "IDENTITE"
            ]):
                return False
            return not is_label_like(upper)

        def _extract_first_date_value(text: str, conf: float = 0.8) -> str:
            sample_block = {"text": text or "", "confidence": conf, "id": -1}
            matches = DocumentStrategy._extract_all_dates([sample_block])
            return matches[0]["value"] if matches else ""

        def _is_place_candidate(value: str) -> bool:
            candidate = (value or "").strip().upper()
            if len(candidate) < 3:
                return False
            if re.search(r'\d{2}[\./-]\d{2}[\./-]\d{2,4}', candidate):
                return False
            if any(token in candidate for token in ["DATE", "EXPIR", "DELIVR", "ISSU", "NAISSANCE"]):
                return False
            return True

        def _extract_sex_value(value: str) -> str:
            compact = re.sub(r"[^A-Z]", "", (value or "").upper())
            if compact in {"M", "MALE", "MASCULIN", "MASC"}:
                return "M"
            if compact in {"F", "FEMALE", "FEMININ", "FEMININE", "FEM"}:
                return "F"

            # Fallback CEDEAO: certains OCR ne capturent pas M/F, mais seulement la nationalité genrée.
            if any(token in compact for token in ["MALIENNE", "GUINEENNE", "IVOIRIENNE", "SENEGALAISE", "BURKINABE"]):
                return "F"
            if any(token in compact for token in ["MALIEN", "GUINEEN", "IVOIRIEN", "SENEGALAIS"]):
                return "M"
            return ""

        # Extraction contextuelle nom/prenom à partir des labels détectés.
        for i, block in enumerate(blocks):
            label_text = normalize_label_text(block.get("text", ""))
            if not label_text:
                continue

            for j in range(i + 1, min(i + 4, len(blocks))):
                candidate = (blocks[j].get("text", "") or "").strip().upper()
                if not is_name_candidate(candidate):
                    continue

                if any(lbl in label_text for lbl in surname_labels) and 'nom' not in extracted:
                    extracted['nom'] = {
                        "value": candidate,
                        "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                        "method": "context_label"
                    }
                    break

                if any(lbl in label_text for lbl in given_labels) and 'prenom' not in extracted:
                    extracted['prenom'] = {
                        "value": candidate,
                        "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                        "method": "context_label"
                    }
                    break

            # Extraction contextuelle du numero d'identite.
            if 'numero_id' not in extracted and any(lbl in label_text for lbl in id_labels):
                for j in range(i + 1, min(i + 4, len(blocks))):
                    raw_candidate = (blocks[j].get("text", "") or "").strip().upper()
                    compact = re.sub(r"[^A-Z0-9]", "", raw_candidate)
                    if re.match(r"^\d{12,20}[A-Z]?$", compact):
                        extracted['numero_id'] = {
                            "value": compact,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break
        
        # Extraction séquentielle prénom + nom (support majuscules OCR), seulement si manquant.
        if 'prenom' not in extracted or 'nom' not in extracted:
            for i in range(len(blocks) - 1):
                word1 = blocks[i]["text"].strip().upper()
                word2 = blocks[i + 1]["text"].strip().upper()
                if is_name_candidate(word1) and is_name_candidate(word2):
                    # Ordre lecture/document: nom puis prénom pour éviter les inversions.
                    nom, prenom = word1, word2
                    if 'prenom' not in extracted:
                        extracted['prenom'] = {
                            "value": prenom,
                            "confidence": round(float(blocks[i + 1].get("confidence", 0.8)), 2),
                            "method": "sequential_uppercase"
                        }
                    if 'nom' not in extracted:
                        extracted['nom'] = {
                            "value": nom,
                            "confidence": round(float(blocks[i].get("confidence", 0.8)), 2),
                            "method": "sequential_uppercase"
                        }
                    if 'prenom' in extracted and 'nom' in extracted:
                        break
        
        # Fallback individuel
        if 'prenom' not in extracted or 'nom' not in extracted:
            candidates = []
            for block in blocks:
                candidate = block["text"].strip().upper()
                if is_name_candidate(candidate):
                    candidates.append((candidate, float(block.get("confidence", 0.0))))

            if candidates:
                candidates = sorted(candidates, key=lambda x: (x[1], len(x[0])), reverse=True)
                if 'prenom' not in extracted:
                    extracted['prenom'] = {"value": candidates[0][0], "confidence": round(candidates[0][1], 2), "method": "fallback_uppercase"}
                if 'nom' not in extracted:
                    nom_candidate = next((c for c in candidates if c[0] != extracted.get('prenom', {}).get('value')), None)
                    if nom_candidate:
                        extracted['nom'] = {"value": nom_candidate[0], "confidence": round(nom_candidate[1], 2), "method": "fallback_uppercase"}
        
        # Dates avec tri chronologique en reutilisant l'extracteur robuste.
        for match in DocumentStrategy._extract_all_dates(blocks):
            value = match.get("value", "")
            date_obj = DocumentStrategy._parse_ddmmyyyy(value)
            if date_obj:
                dates_found.append({
                    "value": value,
                    "date_obj": date_obj
                })
        
        if dates_found:
            dates_found.sort(key=lambda x: x["date_obj"])
            extracted['date_naissance'] = {"value": dates_found[0]["value"], "confidence": 0.85, "method": "regex_date"}
            
            # Si 3 dates ou plus: date_naissance, date_delivrance, date_expiration
            if len(dates_found) >= 3:
                extracted['date_delivrance'] = {"value": dates_found[1]["value"], "confidence": 0.8, "method": "regex_date"}
                extracted['date_expiration'] = {"value": dates_found[-1]["value"], "confidence": 0.8, "method": "regex_date"}
            elif len(dates_found) >= 2:
                extracted['date_expiration'] = {"value": dates_found[-1]["value"], "confidence": 0.8, "method": "regex_date"}

        # Extraction contextuelle des dates et champs CEDEAO (labels bilingues FR/EN).
        birth_labels = ["NAISSANCE", "DATEOFBIRTH", "BIRTH"]
        issuance_labels = ["DELIVRANCE", "DELIVR", "EMISSION", "ISSUANCE", "ISSUE"]
        expiry_labels = ["EXPIRATION", "EXPIRY", "EXPIRE", "EXPLY"]
        sex_labels = ["SEXE", "SEX"]
        place_issuance_labels = ["LIEUDEDELIVRANCE", "PLACEOFISSUANCE", "DELIVRANCE"]

        for i, block in enumerate(blocks):
            label_text = normalize_label_text(block.get("text", ""))
            if not label_text:
                continue

            # Sexe
            if 'sexe' not in extracted and any(lbl in label_text for lbl in sex_labels):
                for j in range(i, min(i + 4, len(blocks))):
                    sex_value = _extract_sex_value(blocks[j].get("text", ""))
                    if sex_value:
                        extracted['sexe'] = {
                            "value": sex_value,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break

            # Date de naissance
            if 'date_naissance' not in extracted and any(lbl in label_text for lbl in birth_labels):
                for j in range(i, min(i + 4, len(blocks))):
                    date_value = _extract_first_date_value(blocks[j].get("text", ""), float(blocks[j].get("confidence", 0.8)))
                    if date_value:
                        extracted['date_naissance'] = {
                            "value": date_value,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break

            # Date de délivrance
            if 'date_delivrance' not in extracted and any(lbl in label_text for lbl in issuance_labels):
                for j in range(i, min(i + 4, len(blocks))):
                    date_value = _extract_first_date_value(blocks[j].get("text", ""), float(blocks[j].get("confidence", 0.8)))
                    if date_value:
                        extracted['date_delivrance'] = {
                            "value": date_value,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break

                    # OCR bruité fréquent: format DD/MMYYYY (ex: 12/012023)
                    noisy_text = (blocks[j].get("text", "") or "").upper().replace(" ", "")
                    noisy_match = re.search(r"\b(\d{1,2})[\./-](\d{2})(\d{4})\b", noisy_text)
                    if noisy_match:
                        day, month, year = noisy_match.groups()
                        try:
                            datetime(int(year), int(month), int(day))
                            extracted['date_delivrance'] = {
                                "value": f"{int(day):02d}/{int(month):02d}/{year}",
                                "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                                "method": "context_label_noisy_date"
                            }
                            break
                        except ValueError:
                            pass

            # Date d'expiration
            if 'date_expiration' not in extracted and any(lbl in label_text for lbl in expiry_labels):
                for j in range(i, min(i + 4, len(blocks))):
                    date_value = _extract_first_date_value(blocks[j].get("text", ""), float(blocks[j].get("confidence", 0.8)))
                    if date_value:
                        extracted['date_expiration'] = {
                            "value": date_value,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break

            # Lieu de délivrance
            if 'lieu_delivrance' not in extracted and any(lbl in label_text for lbl in place_issuance_labels):
                for j in range(i + 1, min(i + 4, len(blocks))):
                    candidate = (blocks[j].get("text", "") or "").strip()
                    if _is_place_candidate(candidate):
                        extracted['lieu_delivrance'] = {
                            "value": candidate,
                            "confidence": round(float(blocks[j].get("confidence", 0.0)), 2),
                            "method": "context_label"
                        }
                        break
        
        # Numéro (alphanumérique 5-20 chars)
        for line in lines:
            num_match = re.search(r'\b[A-Z0-9]{5,20}\b', line.upper().strip())
            if num_match and 'numero_principal' not in extracted:
                if not re.search(r'\d{2}/\d{2}', line):  # Exclure dates
                    numero = num_match.group().strip().upper()
                    # Éviter les faux "numéros" purement textuels issus des en-têtes OCR.
                    if not is_label_like(numero) and re.search(r'\d', numero):
                        extracted['numero_principal'] = {"value": numero, "confidence": 0.75, "method": "regex_alphanum"}
                    break

        # Fallback robuste numero_id: chercher un identifiant long majoritairement numerique.
        if 'numero_id' not in extracted:
            for line in lines:
                compact = re.sub(r"[^A-Z0-9]", "", line.upper())
                if re.match(r"^\d{12,20}[A-Z]?$", compact):
                    extracted['numero_id'] = {
                        "value": compact,
                        "confidence": 0.8,
                        "method": "regex_long_id"
                    }
                    break
        
        # Lieu de naissance: chercher après labels contextuels
        for i, block in enumerate(blocks):
            text = block["text"].upper()
            if any(label in text for label in ["PLACE", "LIEU", "BORN", "NAISSANCE", "LOCUL"]):
                if any(keyword in text for keyword in ["BIRTH", "NAISSANCE", "BORN", "NASTERII"]):
                    # Chercher jusqu'à 3 blocs après
                    for j in range(i + 1, min(i + 4, len(blocks))):
                        candidate = blocks[j]["text"].strip()
                        if (len(candidate) >= 3 and 
                            blocks[j]["confidence"] > 0.8 and
                            not re.search(r'\d{2}/\d{2}/\d{4}', candidate)):
                            extracted['lieu_naissance'] = {
                                "value": candidate.title(),
                                "confidence": round(blocks[j]["confidence"], 2),
                                "method": "context_label"
                            }
                            break
                    if 'lieu_naissance' in extracted:
                        break

        # Fallback global sexe: utile quand le label "Sexe" est bruité et sans valeur M/F explicite.
        if 'sexe' not in extracted:
            for block in blocks:
                sex_value = _extract_sex_value(block.get("text", ""))
                if sex_value:
                    extracted['sexe'] = {
                        "value": sex_value,
                        "confidence": round(float(block.get("confidence", 0.0)), 2),
                        "method": "fallback_nationality_gender"
                    }
                    break
        
        # ============================================================
        # ÉTAPE FINALE: Assigner intelligemment les dates restantes
        # ============================================================
        extracted = DocumentStrategy._assign_dates_intelligently(extracted, blocks)
        
        return extracted
