"""
Parseur MRZ (Machine Readable Zone) pour passeports
Format TD3 (2 lignes de 44 caractères)
"""
import re
import importlib
from typing import Dict, Any, Optional
from datetime import datetime

try:
    _td3_checker_module = importlib.import_module("mrz.checker.td3")
    TD3CodeChecker = getattr(_td3_checker_module, "TD3CodeChecker", None)
except Exception:
    TD3CodeChecker = None

class MRZParser:
    """Parser pour bandes MRZ de passeports"""

    @staticmethod
    def _normalize_td3_line(line: str) -> str:
        cleaned = re.sub(r'[^A-Z0-9<]', '', (line or '').upper().replace(' ', ''))
        if len(cleaned) >= 44:
            return cleaned[:44]
        return cleaned.ljust(44, '<')

    @staticmethod
    def _to_display_date_yy_mm_dd(value: str, prefer_future: bool = False) -> Optional[str]:
        if not value or len(value) != 6 or not value.isdigit():
            return None
        yy, mm, dd = int(value[:2]), int(value[2:4]), int(value[4:6])
        try:
            if prefer_future:
                year = 2000 + yy
            else:
                year = 2000 + yy if yy <= 30 else 1900 + yy
            datetime(year, mm, dd)
            return f"{dd:02d}/{mm:02d}/{year}"
        except Exception:
            return None

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
        Parse MRZ format TD3 (passeport)
        
        Ligne 1:
        - Position 0-1: Type (P pour passeport)
        - Position 2-4: Pays émetteur (MDA, FRA, etc.)
        - Position 5-43: Nom<<Prénom(s)
        
        Ligne 2:
        - Position 0-8: Numéro passeport (AP00000005)
        - Position 10-12: Nationalité
        - Position 13-18: Date naissance AAMMJJ
        - Position 20: Sexe (M/F)
        - Position 21-26: Date expiration AAMMJJ
        - Position 28-41: Numéro personnel (optionnel)
        """
        try:
            # 0) Parser `mrz` prioritaire quand la dependance est disponible.
            parsed_with_lib = MRZParser._parse_td3_with_mrz_lib(line1, line2)
            if parsed_with_lib:
                return parsed_with_lib

            # Nettoyage
            l1 = line1.strip().replace(' ', '')
            l2 = line2.strip().replace(' ', '')
            
            # Validation longueur
            if len(l1) < 30 or len(l2) < 30:
                return None
            
            extracted = {}
            
            # LIGNE 1: Nom et Prénom
            # Format: P<MDA MORARUS<<TATIANA<<<...
            if len(l1) >= 5:
                issuing_country = l1[2:5]
                if re.match(r'^[A-Z]{3}$', issuing_country):
                    extracted['code_pays_emetteur'] = {
                        'value': issuing_country,
                        'confidence': 0.98,
                        'method': 'mrz_line1'
                    }

            name_part = l1[5:44] if len(l1) >= 44 else l1[5:]
            name_parts = [p for p in name_part.split('<') if p]
            
            if len(name_parts) >= 2:
                extracted['nom'] = {
                    'value': name_parts[0],
                    'confidence': 0.98,
                    'method': 'mrz_line1'
                }
                extracted['prenom'] = {
                    'value': name_parts[1],
                    'confidence': 0.98,
                    'method': 'mrz_line1'
                }
            elif len(name_parts) == 1:
                extracted['nom'] = {
                    'value': name_parts[0],
                    'confidence': 0.98,
                    'method': 'mrz_line1'
                }
            
            # LIGNE 2: Numéro, dates, sexe
            # Format TD3: 2 lettres + chiffres variables (6-9 selon pays)
            # Exemple: AP0000000<MDA... ou AP00000005<MDA...
            # Positions 0-8 (9 chars max): Numéro passeport
            
            # Numéro passeport: TD3 standard = 2 lettres + 7 chiffres (+ 1 checksum digit)
            # Exemple: AP0000000 (vrai numéro) + 5 (checksum) = AP00000005 dans MRZ
            numero_match = re.match(r'^([A-Z]{2}\d{7})', l2)
            if numero_match:
                numero = numero_match.group(0)
                extracted['numero_passeport'] = {
                    'value': numero,
                    'confidence': 0.98,
                    'method': 'mrz_line2'
                }
            
            # Date de naissance (positions 13-18: AAMMJJ)
            nat_code = l2[10:13] if len(l2) >= 13 else None
            if nat_code and re.match(r'^[A-Z]{3}$', nat_code):
                extracted['code_pays'] = {
                    'value': nat_code,
                    'confidence': 0.98,
                    'method': 'mrz_line2'
                }

            dob_str = l2[13:19] if len(l2) >= 19 else None
            if dob_str and dob_str.isdigit() and len(dob_str) == 6:
                try:
                    yy, mm, dd = dob_str[0:2], dob_str[2:4], dob_str[4:6]
                    # Déterminer siècle (00-30 → 2000, 31-99 → 1900)
                    year = int(yy)
                    full_year = 2000 + year if year <= 30 else 1900 + year
                    
                    # Validation date
                    date_obj = datetime(full_year, int(mm), int(dd))
                    extracted['date_naissance'] = {
                        'value': f"{dd}/{mm}/{full_year}",
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
                except:
                    pass
            
            # Date expiration (positions 21-26: AAMMJJ)
            exp_str = l2[21:27] if len(l2) >= 27 else None
            if exp_str and exp_str.isdigit() and len(exp_str) == 6:
                try:
                    yy, mm, dd = exp_str[0:2], exp_str[2:4], exp_str[4:6]
                    year = int(yy)
                    # Pour une date d'expiration, toujours dans le futur (2000+)
                    full_year = 2000 + year
                    
                    date_obj = datetime(full_year, int(mm), int(dd))
                    extracted['date_expiration'] = {
                        'value': f"{dd}/{mm}/{full_year}",
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
                except:
                    pass
            
            # Sexe (position 20)
            if len(l2) >= 21:
                sexe = l2[20]
                if sexe in ['M', 'F']:
                    extracted['sexe'] = {
                        'value': sexe,
                        'confidence': 0.98,
                        'method': 'mrz_line2'
                    }
            
            return extracted if extracted else None
            
        except Exception as e:
            return None
    
    @staticmethod
    def find_mrz_blocks(blocks: list) -> Optional[tuple]:
        """
        Trouve les 2 lignes MRZ parmi les blocks
        Critères:
        - 2 blocks consécutifs (spatially)
        - Contiennent '<' (caractère MRZ)
        - Longueur >= 30 caractères
        - Haute confiance
        """
        mrz_candidates = []
        
        for block in blocks:
            text = block['text']
            # MRZ contient des '<' et fait >= 30 chars
            if '<' in text and len(text) >= 30 and block['confidence'] > 0.6:
                mrz_candidates.append(block)
        
        # Chercher 2 blocks consécutifs verticalement
        if len(mrz_candidates) >= 2:
            # Trier par position Y
            mrz_candidates.sort(key=lambda b: b['bbox'][0][1])
            
            # Vérifier si les 2 premiers sont proches verticalement
            for i in range(len(mrz_candidates) - 1):
                b1, b2 = mrz_candidates[i], mrz_candidates[i+1]
                y1 = b1['bbox'][2][1]  # Bottom Y de block 1
                y2 = b2['bbox'][0][1]  # Top Y de block 2
                
                # Si moins de 50px d'écart vertical
                if abs(y2 - y1) < 50:
                    return (b1['text'], b2['text'])
        
        return None
