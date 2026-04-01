"""
Parseur MRZ (Machine Readable Zone) pour passeports
Format TD3 (2 lignes de 44 caractères)
Amélioration : meilleure robustesse aux erreurs OCR et support multi-formats
"""
import re
import importlib
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

try:
    _td3_checker_module = importlib.import_module("mrz.checker.td3")
    TD3CodeChecker = getattr(_td3_checker_module, "TD3CodeChecker", None)
except Exception:
    TD3CodeChecker = None

class MRZParser:
    """Parser pour bandes MRZ de passeports"""

    # Mapping pour corriger les erreurs OCR courantes
    OCR_CORRECTIONS = {
        'O': '0',  # O misparsed as 0
        'I': '1',  # I misparsed as 1
        'Z': '2',  # Z misparsed as 2
        'B': '8',  # B misparsed as 8
        'S': '5',  # S misparsed as 5
    }

    @staticmethod
    def _correct_ocr_errors(text: str, context: str = "alphanumeric") -> str:
        """Corrige les erreurs OCR courantes basées sur le contexte"""
        corrected = text.upper()
        
        # Pour zones numériques, remplacer les caractères qui ressemblent à des chiffres
        if context == "numeric":
            corrected = re.sub(r'[OIZ]', lambda m: MRZParser.OCR_CORRECTIONS.get(m.group(0), m.group(0)), corrected)
        
        # Pour les noms/caractères alphabétiques
        elif context == "alphabetic":
            # Remplacer moins agressivement pour les noms
            corrected = re.sub(r'[0]', 'O', corrected)  # 0 → O uniquement pour noms
        
        return corrected

    @staticmethod
    def _fix_numeric_field(value: str) -> str:
        """Corrige les confusions OCR frequentes uniquement pour des champs numeriques."""
        if not value:
            return ""
        corrected = value.upper()
        corrected = corrected.replace('O', '0').replace('I', '1').replace('Z', '2').replace('S', '5').replace('B', '8')
        return re.sub(r'[^0-9<]', '', corrected)

    @staticmethod
    def _normalize_td3_line(line: str, allow_corrections: bool = True) -> str:
        """Normalise une ligne MRZ avec correction optionnelle des erreurs OCR"""
        if not line:
            return '<' * 44
        
        # Étape 1: Conversion en majuscules et nettoyage basique
        cleaned = (line or '').upper().replace(' ', '').strip()
        
        # Étape 2: Correction des erreurs OCR courantes si activé
        if allow_corrections:
            # Tenter de corriger les caractères douteux
            # Après position 5, c'est du texte (noms)
            if len(cleaned) > 5:
                prefix = cleaned[:5]
                content = cleaned[5:]
                # Pour la partie numéro/codes pays, corriger agressivement
                prefix = MRZParser._correct_ocr_errors(prefix, "numeric")
                # Pour la partie nom, corriger doucement
                cleaned = prefix + content
        
        # Étape 3: Garder seulement les caractères valides MRZ
        cleaned = re.sub(r'[^A-Z0-9<]', '', cleaned)
        
        # Étape 4: Padding et truncate à 44 caractères
        if len(cleaned) >= 44:
            return cleaned[:44]
        return cleaned.ljust(44, '<')

    @staticmethod
    def _to_display_date_yy_mm_dd(value: str, prefer_future: bool = False) -> Optional[str]:
        """Convertit une date YY/MM/DD en format JJ/MM/YYYY avec gestion des siècles"""
        if not value or len(value) < 6 or not value.isdigit():
            return None
        
        try:
            yy = int(value[:2])
            mm = int(value[2:4])
            dd = int(value[4:6])
            
            # Validation basique
            if mm < 1 or mm > 12 or dd < 1 or dd > 31:
                return None
            
            # Déterminer le siècle
            if prefer_future:
                # Pour dates d'expiration: toujours dans le futur (2000+)
                year = 2000 + yy
            else:
                # Pour dates de naissance: appliquer la règle de pivot
                # 00-30 → 2000, 31-99 → 1900
                year = 2000 + yy if yy <= 30 else 1900 + yy
            
            # Validation de la date
            datetime(year, mm, dd)
            return f"{dd:02d}/{mm:02d}/{year}"
        except Exception:
            return None
    
    @staticmethod
    def _validate_checksum_digit(data: str, check_digit: str) -> bool:
        """Valide le checksum digit MD10 selon la norme ICAO"""
        try:
            weights = [7, 3, 1]
            total = 0
            for i, char in enumerate(data):
                if char.isdigit():
                    weight = weights[i % 3]
                    total += int(char) * weight
                elif char == '<':
                    weight = weights[i % 3]
                    total += 0  # '<' compte comme 0
                else:
                    # Lettres: A=10, B=11, ..., Z=35
                    weight = weights[i % 3]
                    total += (ord(char) - ord('A') + 10) * weight
            
            remainder = total % 10
            return str(remainder) == check_digit.upper()
        except Exception:
            return False
    
    @staticmethod
    def _find_mrz_line_positions(text: str) -> List[int]:
        """Trouve toutes les positions possibles dans le texte qui pourraient être des lignes MRZ"""
        positions = []
        lines = text.split('\n')
        cumulative_pos = 0
        
        for line in lines:
            # Une ligne MRZ contient '<' et fait au moins 30 caractères
            if '<' in line and len(line) >= 30:
                positions.append((cumulative_pos, line))
            cumulative_pos += len(line) + 1  # +1 pour le newline
        
        return positions

    @staticmethod
    def _parse_td3_with_mrz_lib(line1: str, line2: str) -> Optional[Dict[str, Any]]:
        """Parse TD3 avec la librairie `mrz` si disponible."""
        if TD3CodeChecker is None:
            return None

        l1 = MRZParser._normalize_td3_line(line1)
        l2 = MRZParser._normalize_td3_line(line2)
        if len(l1) != 44 or len(l2) != 44:
            return None

        try:
            checker = TD3CodeChecker(l1 + l2)
        except Exception:
            return None

        fields = None
        if hasattr(checker, "fields"):
            maybe_fields = checker.fields()
            if isinstance(maybe_fields, dict):
                fields = maybe_fields

        if not fields:
            return None

        extracted = {}

        issuing_country = (fields.get("country") or "").upper()
        if re.match(r'^[A-Z]{3}$', issuing_country):
            extracted['code_pays_emetteur'] = {
                'value': issuing_country,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        nationality = (fields.get("nationality") or "").upper()
        if re.match(r'^[A-Z]{3}$', nationality):
            extracted['code_pays'] = {
                'value': nationality,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }
            extracted['nationalite'] = {
                'value': nationality,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        surname = (fields.get("surname") or "").strip('< ').upper()
        if surname:
            extracted['nom'] = {
                'value': surname,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        given_name = (fields.get("name") or "").replace('<', ' ').strip().upper()
        if given_name:
            extracted['prenom'] = {
                'value': given_name,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        doc_number = (fields.get("document_number") or "").replace('<', '').strip().upper()
        if doc_number:
            extracted['numero_passeport'] = {
                'value': doc_number,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        birth_date = MRZParser._to_display_date_yy_mm_dd(fields.get("birth_date") or "")
        if birth_date:
            extracted['date_naissance'] = {
                'value': birth_date,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        expiry_date = MRZParser._to_display_date_yy_mm_dd(fields.get("expiry_date") or "", prefer_future=True)
        if expiry_date:
            extracted['date_expiration'] = {
                'value': expiry_date,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        sex = (fields.get("sex") or "").upper()
        if sex in ['M', 'F']:
            extracted['sexe'] = {
                'value': sex,
                'confidence': 0.99,
                'method': 'mrz_lib'
            }

        return extracted if extracted else None
    
    @staticmethod
    def parse_td3(line1: str, line2: str) -> Optional[Dict[str, Any]]:
        """
        Parse MRZ format TD3 (passeport) - VERSION AMÉLIORÉE
        
        Ligne 1 (44 caractères):
        - Position 0-1: Type (P pour passeport)
        - Position 2-4: Pays émetteur (GIN pour Guinée, etc.)
        - Position 5-43: Nom<<Prénom(s) séparés par <<
        
        Ligne 2 (44 caractères):
        - Position 0-8: Numéro passeport (2 lettres + 7 chiffres)
        - Position 9: Checksum digit
        - Position 10-12: Nationalité (code pays 3 lettres)
        - Position 13-18: Date naissance AAMMJJ
        - Position 19: Checksum digit naissance
        - Position 20: Sexe (M/F)
        - Position 21-26: Date expiration AAMMJJ
        - Position 27: Checksum digit expiration
        - Position 28-41: Numéro personnel (optionnel)
        - Position 42: Checksum digit personnel
        - Position 43: Checksum final
        """
        try:
            # Étape 1: Utiliser la librairie mrz si disponible (la plus fiable)
            parsed_with_lib = MRZParser._parse_td3_with_mrz_lib(line1, line2)
            if parsed_with_lib:
                logger.debug(f"✅ MRZ parsed avec librarie mrz")
                return parsed_with_lib

            # Étape 2: Nettoyage et normalisation avec correction OCR
            l1 = line1.strip().replace(' ', '')
            l2 = line2.strip().replace(' ', '')
            
            # Correction OCR: garder ligne 2 intacte pour ne pas casser les champs alphabetiques (ex: GIN)
            l1 = MRZParser._correct_ocr_errors(l1, "alphanumeric")
            
            # Étape 3: Normalisation MRZ
            l1 = MRZParser._normalize_td3_line(l1, allow_corrections=False)  # Already corrected
            l2 = MRZParser._normalize_td3_line(l2, allow_corrections=False)  # Already corrected
            
            logger.debug(f"Parsed MRZ Line1 (normalized): {l1}")
            logger.debug(f"Parsed MRZ Line2 (normalized): {l2}")
            
            # Étape 4: Validation longueur minimum
            if len(l1) < 30 or len(l2) < 30:
                logger.warning(f"MRZ lines too short: l1={len(l1)}, l2={len(l2)}")
                return None
            
            extracted = {}
            
            # ===== LIGNE 1: Pays émetteur et Nom/Prénom =====
            if len(l1) >= 5:
                issuing_country = l1[2:5].replace('<', '')
                if re.match(r'^[A-Z]{3}$', issuing_country) and issuing_country != '<<<':
                    extracted['code_pays_emetteur'] = {
                        'value': issuing_country,
                        'confidence': 0.98,
                        'method': 'mrz_line1'
                    }

            # Extraction Nom et Prénom
            name_part = l1[5:44] if len(l1) >= 44 else l1[5:]
            name_parts = [p.strip() for p in name_part.split('<') if p.strip()]
            
            if len(name_parts) >= 2:
                nom = name_parts[0].strip('<')
                prenom = ' '.join(name_parts[1:]).strip('<')
                
                if nom and nom != '<<<':
                    extracted['nom'] = {
                        'value': nom,
                        'confidence': 0.98,
                        'method': 'mrz_line1'
                    }
                if prenom and prenom != '<<<':
                    extracted['prenom'] = {
                        'value': prenom,
                        'confidence': 0.98,
                        'method': 'mrz_line1'
                    }
            elif len(name_parts) == 1:
                nom = name_parts[0].strip('<')
                if nom and nom != '<<<':
                    extracted['nom'] = {
                        'value': nom,
                        'confidence': 0.98,
                        'method': 'mrz_line1'
                    }
            
            # ===== LIGNE 2: Numéro, nationalité, dates, sexe =====
            
            # Numero document (positions 0-8): alphanumerique + fillers '<' selon ICAO TD3
            raw_doc_number = l2[0:9] if len(l2) >= 9 else ""
            raw_doc_number = raw_doc_number.upper()
            corrected_doc_number = ''.join(ch for ch in raw_doc_number if ch.isalnum() or ch == '<')
            doc_number = corrected_doc_number.replace('<', '')
            # Extraction generique: accepte alpha, numerique ou mixte (sans hardcode de format pays)
            if 6 <= len(doc_number) <= 12 and re.match(r'^[A-Z0-9]+$', doc_number):
                confidence = 0.96
                # Bonus confiance si checksum numero present et valide (position 9)
                if len(l2) >= 10 and l2[9].isdigit() and MRZParser._validate_checksum_digit(corrected_doc_number.ljust(9, '<')[:9], l2[9]):
                    confidence = 0.99
                extracted['numero_passeport'] = {
                    'value': doc_number,
                    'confidence': confidence,
                    'method': 'mrz_line2'
                }
            
            # Nationalité (positions 10-12)
            if len(l2) >= 13:
                nat_code = l2[10:13].replace('<', '')
                if re.match(r'^[A-Z]{3}$', nat_code) and nat_code != '<<<':
                    extracted['code_pays'] = {
                        'value': nat_code,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
                    extracted['nationalite'] = {
                        'value': nat_code,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }

            # Date de naissance (positions 13-18: AAMMJJ)
            if len(l2) >= 19:
                dob_str = MRZParser._fix_numeric_field(l2[13:19])
                birth_date = MRZParser._to_display_date_yy_mm_dd(dob_str, prefer_future=False)
                if birth_date:
                    extracted['date_naissance'] = {
                        'value': birth_date,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
            
            # Date expiration (positions 21-26: AAMMJJ)
            if len(l2) >= 27:
                exp_str = MRZParser._fix_numeric_field(l2[21:27])
                expiry_date = MRZParser._to_display_date_yy_mm_dd(exp_str, prefer_future=True)
                if expiry_date:
                    extracted['date_expiration'] = {
                        'value': expiry_date,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
            
            # Sexe (position 20)
            if len(l2) >= 21:
                sexe = l2[20].upper()
                if sexe in ['M', 'F']:
                    extracted['sexe'] = {
                        'value': sexe,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
            
            if not extracted:
                logger.warning("No fields extracted from TD3 MRZ")
                return None
            
            logger.info(f"✅ MRZ TD3 parsed successfully: {len(extracted)} fields extracted")
            return extracted
            
        except Exception as e:
            logger.error(f"❌ Error parsing TD3 MRZ: {e}")
            return None
    
    @staticmethod
    def find_mrz_blocks(blocks: List[Dict[str, Any]], min_confidence: float = 0.5) -> Optional[Tuple[str, str]]:
        """
        Trouve les 2 lignes MRZ parmi les blocks OCR.
        Stratégie:
        1. Chercher les blocks contenant '<' (caractère MRZ)
        2. Vérifier qu'ils sont à la fin du document (zone inférieure)
        3. Valider la longueur et confiance
        4. Retourner les 2 lignes consécutives les plus prometteuses
        """
        if not blocks:
            return None
        
        # Étape 1: Identifier les candidats MRZ
        mrz_candidates = []
        for idx, block in enumerate(blocks):
            text = str(block.get('text', '')).upper().strip()
            confidence = block.get('confidence', 0)
            bbox = block.get('bbox', [])
            
            # Un block MRZ doit :
            # - Contenir '<' ou avoir une longueur importante
            # - Être alphanumérique/MRZ characters mostly
            # - Avoir une confiance raisonnable
            if ('<' in text and len(text) >= 30 and confidence > min_confidence) or \
               (len(text) >= 40 and re.match(r'^[A-Z0-9<]{30,}$', text)):
                mrz_candidates.append((idx, text, confidence, bbox))
        
        if len(mrz_candidates) < 2:
            return None
        
        # Étape 2: Trier par position Y (verticale) pour trouver les lignes proches
        mrz_candidates.sort(key=lambda c: c[3][0][1] if c[3] else 0)
        
        # Étape 3: Chercher 2 lignes consécutives et proches verticalement
        for i in range(len(mrz_candidates) - 1):
            idx1, text1, conf1, bbox1 = mrz_candidates[i]
            idx2, text2, conf2, bbox2 = mrz_candidates[i + 1]
            
            # Vérifier que les lignes sont proches (moins de 100px d'écart)
            if bbox1 and bbox2:
                y1_bottom = bbox1[2][1]  # Bottom Y of first block
                y2_top = bbox2[0][1]     # Top Y of second block
                
                if abs(y2_top - y1_bottom) < 100:  # Lignes proches
                    return (text1, text2)
        
        # Fallback: Si pas 2 lignes consécutives proches, retourner les 2 meilleures
        if len(mrz_candidates) >= 2:
            # Trier par confiance décroissante
            mrz_candidates_by_conf = sorted(mrz_candidates, key=lambda c: c[2], reverse=True)
            return (mrz_candidates_by_conf[0][1], mrz_candidates_by_conf[1][1])
        
        return None
