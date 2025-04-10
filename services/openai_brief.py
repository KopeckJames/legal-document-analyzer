"""
Simple and reliable OpenAI service specifically for brief generation.
This module is designed to be maximally reliable with minimal dependencies.
"""
import os
import logging
import json
from datetime import datetime

logger = logging.getLogger(__name__)

def generate_brief_with_openai(document_text, title, focus_areas=None, document_id=None):
    """
    Generate a legal brief using OpenAI API.
    
    Args:
        document_text (str): The text content of the document
        title (str): Title for the brief
        focus_areas (list, optional): List of areas to focus on in the brief
        document_id (int, optional): Document ID to fetch related statutes
        
    Returns:
        tuple: (content, summary, enhanced_summary, key_insights, action_items)
    """
    try:
        # Verify OpenAI API key is available
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OpenAI API key not found in environment")
            raise ValueError("OpenAI API key is required but not found")
        
        # Import OpenAI library
        try:
            from openai import OpenAI
        except ImportError as e:
            logger.error(f"Failed to import OpenAI: {e}")
            raise ImportError(f"OpenAI library not available: {e}")
        
        # Create client
        client = OpenAI(api_key=api_key)
        
        # Prepare document text (truncate if too long)
        if len(document_text) > 5000:
            logger.info(f"Truncating document text from {len(document_text)} to 5000 chars")
            doc_content = document_text[:5000] + "... [Content truncated for API limits]"
        else:
            doc_content = document_text
        
        # Prepare focus areas text
        focus_areas_text = ""
        if focus_areas and isinstance(focus_areas, list):
            focus_areas_text = "Focus especially on these areas:\n" + "\n".join([f"- {area}" for area in focus_areas])
            logger.info(f"Focus areas: {focus_areas}")
        else:
            logger.info("No focus areas specified")
        
        # Get statutes if document_id is provided
        statutes_text = "Relevant Statutes and Regulations:\n"
        if document_id:
            try:
                # Import needed here to avoid circular imports
                from models import Statute
                from app import app, db
                
                # Use application context to ensure DB operations happen within scope
                with app.app_context():
                    statutes = Statute.query.filter_by(document_id=document_id).all()
                    if statutes:
                        for statute in statutes:
                            status = "CURRENT" if statute.is_current else "OUTDATED"
                            statutes_text += f"- {statute.reference} [{status}]\n"
                            
                            if statute.content:
                                # Add a snippet of the context
                                context = statute.content
                                if len(context) > 150:
                                    context = context[:150] + "..."
                                statutes_text += f"  Context: {context}\n"
                        
                        logger.info(f"Found {len(statutes)} statutes for document {document_id}")
                    else:
                        # Provide placeholder text to ensure the section is created
                        statutes_text += "No specific statute or regulation references were identified in this document.\n"
                        statutes_text += "Note: Legal analysis may still be applicable even without specific statute references.\n"
                        statutes_text += "Always consult with a qualified legal professional for a comprehensive review."
                        logger.info(f"No statutes found for document {document_id}, using placeholder text")
            except Exception as e:
                # Provide fallback text in case of errors
                statutes_text += "Unable to retrieve statute references due to a technical issue.\n"
                statutes_text += "Please review the document for any referenced statutes or regulations."
                logger.warning(f"Error retrieving statutes: {e}")
        
        # Construct the prompt
        prompt = f"""Create a detailed legal brief based on the following document content.
            
Document title: {title}

{focus_areas_text}

{statutes_text}

Structure the brief with these sections:
1. Introduction
2. Factual Background
3. Legal Issues
4. Legal Analysis
5. Conclusion
6. Statutes and Regulations (ALWAYS include this section)

Document content: {doc_content}

Please format the brief in Markdown with appropriate headings. 
If statutes are provided above, be sure to analyze them in your legal analysis and include them in the Statutes section."""
        
        # Call OpenAI API
        logger.info("Calling OpenAI API to generate brief content")
        response = client.chat.completions.create(
            model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
            messages=[
                {"role": "system", "content": "You are a legal brief writer."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000
        )
        
        # Extract content
        content = response.choices[0].message.content
        logger.info(f"Received {len(content)} chars of content from OpenAI")
        
        # Create a simple summary from the first paragraphs
        summary_paragraphs = []
        for line in content.split('\n'):
            if line.strip() and not line.startswith('#'):
                summary_paragraphs.append(line.strip())
                if len(' '.join(summary_paragraphs)) > 200:
                    break
        
        summary = ' '.join(summary_paragraphs)
        if len(summary) > 300:
            summary = summary[:297] + '...'
            
        # Now generate enhanced summaries and insights using a separate API call
        logger.info("Generating enhanced summaries and insights")
        summary_prompt = f"""
        Please analyze the following legal brief and provide:
        
        1. ENHANCED SUMMARY: A detailed executive summary (500-700 characters) that captures the key points and conclusions.
        2. KEY INSIGHTS: 3-5 bullet points of the most important legal insights from the brief.
        3. ACTION ITEMS: 2-4 recommended next steps or actions based on the legal analysis.
        
        Format the response as JSON with keys "enhanced_summary", "key_insights", and "action_items".
        
        Legal brief:
        {content}
        """
        
        try:
            # Call OpenAI API for enhanced summary
            summary_response = client.chat.completions.create(
                model="gpt-4o",  # the newest OpenAI model is "gpt-4o" which was released May 13, 2024
                messages=[
                    {"role": "system", "content": "You are a legal expert who creates concise, insightful summaries of legal documents."},
                    {"role": "user", "content": summary_prompt}
                ],
                temperature=0.3,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            
            # Parse the JSON response
            summary_content = summary_response.choices[0].message.content
            summary_data = json.loads(summary_content)
            
            enhanced_summary = summary_data.get("enhanced_summary", "")
            key_insights = summary_data.get("key_insights", "")
            action_items = summary_data.get("action_items", "")
            
            # Format the key insights and action items as markdown
            if isinstance(key_insights, list):
                key_insights = "\n".join([f"- {insight}" for insight in key_insights])
            
            if isinstance(action_items, list):
                action_items = "\n".join([f"- {item}" for item in action_items])
                
            logger.info("Enhanced summaries generated successfully")
        except Exception as e:
            logger.error(f"Error generating enhanced summaries: {e}", exc_info=True)
            enhanced_summary = "An error occurred while generating the enhanced summary."
            key_insights = "Unable to extract key insights at this time."
            action_items = "Please review the full brief for recommended actions."
        
        # Add generation note
        content += f"\n\n---\n*This brief was automatically generated on {datetime.utcnow().strftime('%Y-%m-%d')} with AI assistance. " \
                  f"It should be reviewed for accuracy and completeness.*"
        
        logger.info("Brief generation completed successfully")
        return content, summary, enhanced_summary, key_insights, action_items
        
    except Exception as e:
        logger.error(f"Error in generate_brief_with_openai: {e}", exc_info=True)
        raise Exception(f"Failed to generate brief with OpenAI: {e}")