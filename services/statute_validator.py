import requests
import logging
import re
import os
import json
from datetime import datetime
from models import Statute
from openai import OpenAI

logger = logging.getLogger(__name__)

def validate_statutes(statute_references, document_id):
    """
    Validate a list of statute references against legal databases.
    
    Args:
        statute_references (list): List of statute reference dictionaries
        document_id (int): The document ID
        
    Returns:
        list: List of updated Statute model instances
    """
    logger.info(f"Validating {len(statute_references)} statutes for document ID: {document_id}")
    
    # Get existing statutes for this document
    from app import db
    existing_statutes = Statute.query.filter_by(document_id=document_id).all()
    existing_refs = {s.reference: s for s in existing_statutes}
    
    updated_statutes = []
    
    # Process each statute reference
    for statute_data in statute_references:
        reference = statute_data['reference']
        
        # Check if we already have this statute
        if reference in existing_refs:
            statute = existing_refs[reference]
        else:
            # Create a new statute record
            statute = Statute(
                reference=reference,
                content=statute_data.get('context', ''),
                document_id=document_id,
                is_current=True,  # Default to true until checked
                verified_at=datetime.utcnow()
            )
            db.session.add(statute)
        
        # Validate the statute against legal databases
        try:
            is_current, source_db = check_statute_currency(reference)
            
            # Update the statute record
            statute.is_current = is_current
            statute.source_database = source_db
            statute.verified_at = datetime.utcnow()
            
            updated_statutes.append(statute)
            
        except Exception as e:
            logger.error(f"Error validating statute {reference}: {str(e)}")
            # Mark as current but note the validation issue
            statute.is_current = True  # Assume valid in case of error
            statute.source_database = "Validation Error"
            statute.verified_at = datetime.utcnow()
            
            updated_statutes.append(statute)
    
    # Commit all updates
    try:
        db.session.commit()
    except Exception as e:
        logger.error(f"Error committing statute updates: {str(e)}")
        db.session.rollback()
    
    return updated_statutes

def revalidate_statute(statute):
    """
    Revalidate a specific statute against legal databases.
    
    Args:
        statute (Statute): The statute to revalidate
        
    Returns:
        Statute: The updated statute
    """
    logger.info(f"Revalidating statute ID: {statute.id}, Ref: {statute.reference}")
    
    try:
        # Validate the statute against legal databases
        is_current, source_db = check_statute_currency(statute.reference)
        
        # Update the statute record
        statute.is_current = is_current
        statute.source_database = source_db
        statute.verified_at = datetime.utcnow()
        
        # Commit the update
        from app import db
        db.session.commit()
        
        return statute
        
    except Exception as e:
        logger.error(f"Error revalidating statute {statute.reference}: {str(e)}")
        raise ValueError(f"Failed to revalidate statute: {str(e)}")

def validate_with_openai(reference):
    """
    Use OpenAI to validate a statute reference when no legal API is available.
    
    Args:
        reference (str): The statute reference to check
        
    Returns:
        tuple: (is_current, source_database)
    """
    # Get OpenAI API key from environment
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    
    if not openai_api_key:
        logger.warning("No OpenAI API key available for statute validation")
        return mock_validate_statute(reference)
    
    try:
        client = OpenAI(api_key=openai_api_key)
        
        prompt = f"""
As a legal expert, verify if this legal citation is current or outdated: "{reference}"

Analyze the citation format and respond with:
1. Is this statute/regulation still in effect? (true/false)
2. What legal database would typically be used to verify this?
3. Your confidence level (0.0-1.0) in this assessment

IMPORTANT: Return ONLY a JSON object with these three fields:
- is_current: boolean
- source_database: string
- confidence: float
"""
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-4o",  # Use the latest model for best legal knowledge
            messages=[
                {"role": "system", "content": "You are a legal research expert who verifies statute and regulation citations."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.2  # Lower temperature for more factual responses
        )
        
        # Parse the response
        try:
            result = json.loads(response.choices[0].message.content)
            is_current = result.get('is_current', True)
            source_database = result.get('source_database', 'OpenAI Legal Validation')
            confidence = result.get('confidence', 0.0)
            
            logger.info(f"OpenAI validation for '{reference}': is_current={is_current}, confidence={confidence}")
            
            # If confidence is too low, default to "current" for safety
            if confidence < 0.6:
                logger.warning(f"Low confidence ({confidence}) in validation of '{reference}', defaulting to current")
                is_current = True
                source_database = f"OpenAI (Low Confidence: {confidence})"
            else:
                source_database = f"OpenAI Legal Validation"
                
            return is_current, source_database
            
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing OpenAI validation response: {str(e)}")
            return True, "OpenAI Parsing Error"
            
    except Exception as e:
        logger.error(f"Error using OpenAI for statute validation: {str(e)}")
        return True, "OpenAI Error"

def check_statute_currency(reference):
    """
    Check if a statute reference is current by querying legal databases.
    
    Args:
        reference (str): The statute reference to check
        
    Returns:
        tuple: (is_current, source_database)
    """
    # Get API key from environment
    api_key = os.environ.get('LEGAL_API_KEY')
    
    # Try OpenAI validation if legal API key is not available
    if not api_key and os.environ.get('OPENAI_API_KEY'):
        logger.info(f"No LEGAL_API_KEY found, using OpenAI to validate statute: {reference}")
        return validate_with_openai(reference)
    elif not api_key:
        logger.warning("No LEGAL_API_KEY or OPENAI_API_KEY found, using mock validation")
        return mock_validate_statute(reference)
    
    # Determine which API to use based on the reference format
    if re.search(r'U\.?S\.?C\.?', reference):
        # US Code reference
        return check_uscode_statute(reference, api_key)
    elif re.search(r'C\.?F\.?R\.?', reference):
        # Code of Federal Regulations
        return check_cfr_statute(reference, api_key)
    else:
        # Other types of references
        return check_general_statute(reference, api_key)

def check_uscode_statute(reference, api_key):
    """Check a US Code statute reference."""
    # Extract the title and section
    match = re.search(r'(\d+)\s+U\.?S\.?C\.?\s+§\s*(\d+[a-z]*)', reference)
    
    if not match:
        logger.warning(f"Could not parse USC reference: {reference}")
        return True, "Parse Error"
    
    title = match.group(1)
    section = match.group(2)
    
    # Query the US Code API
    try:
        api_url = f"https://api.law.gov/uscode/v1/titles/{title}/sections/{section}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # Check if the statute is current
            return data.get('is_current', True), "US Code API"
        elif response.status_code == 404:
            # Statute not found - may be repealed or invalid
            return False, "US Code API"
        else:
            logger.warning(f"US Code API returned status {response.status_code}: {response.text}")
            return True, "API Error"
            
    except Exception as e:
        logger.error(f"Error querying US Code API: {str(e)}")
        return True, "API Error"

def check_cfr_statute(reference, api_key):
    """Check a Code of Federal Regulations reference."""
    # Extract the title and part/section
    match = re.search(r'(\d+)\s+C\.?F\.?R\.?\s+§\s*(\d+\.\d+)', reference)
    
    if not match:
        logger.warning(f"Could not parse CFR reference: {reference}")
        return True, "Parse Error"
    
    title = match.group(1)
    section = match.group(2)
    
    # Query the CFR API
    try:
        api_url = f"https://api.law.gov/cfr/v1/titles/{title}/sections/{section}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        
        response = requests.get(api_url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # Check if the regulation is current
            return data.get('is_current', True), "CFR API"
        elif response.status_code == 404:
            # Regulation not found - may be repealed or invalid
            return False, "CFR API"
        else:
            logger.warning(f"CFR API returned status {response.status_code}: {response.text}")
            return True, "API Error"
            
    except Exception as e:
        logger.error(f"Error querying CFR API: {str(e)}")
        return True, "API Error"

def check_general_statute(reference, api_key):
    """Check a general statute reference."""
    # Query a general law database API
    try:
        api_url = "https://api.law.gov/search/v1/statutes"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        params = {
            "q": reference,
            "fields": "reference,status"
        }
        
        response = requests.get(api_url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            
            if results:
                # Check status of the first matching result
                return results[0].get('status') == 'current', "General Statute API"
            else:
                # No matches found
                logger.warning(f"No matches found for reference: {reference}")
                return True, "No Match Found"
        else:
            logger.warning(f"General Statute API returned status {response.status_code}: {response.text}")
            return True, "API Error"
            
    except Exception as e:
        logger.error(f"Error querying General Statute API: {str(e)}")
        return True, "API Error"

def mock_validate_statute(reference):
    """
    Mock implementation for statute validation when no API key is available.
    
    This uses pattern matching to make educated guesses about statute currency.
    In a production environment, this would be replaced with actual API calls.
    """
    logger.info(f"Using mock validation for statute: {reference}")
    
    # Some references that we'll mark as outdated for demonstration
    outdated_patterns = [
        r'12\s+U\.?S\.?C\.?\s+§\s*24[a-c]',  # Example outdated banking statute
        r'18\s+U\.?S\.?C\.?\s+§\s*152[0-5]',  # Example outdated criminal statute
        r'21\s+C\.?F\.?R\.?\s+§\s*101\.1[0-5]',  # Example outdated FDA regulation
        r'Pub\.?\s+L(?:aw)?\.?\s+105-',  # Example outdated public law
    ]
    
    # Check if the reference matches any outdated pattern
    for pattern in outdated_patterns:
        if re.search(pattern, reference):
            return False, "Mock Validation"
    
    # Default to current
    return True, "Mock Validation"
