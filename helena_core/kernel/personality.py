# helena_core/kernel/personality.py
"""
HELENA's personality system – dry technical wit, adaptive responses,
and emotion-aware output.

Integrates with EmotionEngine to modulate tone, verbosity, and humor
based on HELENA's current emotional state.
"""
import random
import time
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum, auto
import logging

if TYPE_CHECKING:
    from helena_core.kernel.emotion import EmotionEngine

logger = logging.getLogger(__name__)

class PersonalityTrait(Enum):
    """Personality traits"""
    VERBOSITY = auto()          # How much to say
    TECHNICAL_DEPTH = auto()    # How technical to be
    HUMOR_FREQUENCY = auto()    # How often to be humorous
    CREATIVITY = auto()         # How creative to be
    FORMALITY = auto()          # How formal to be
    PATIENCE = auto()           # How patient to be

@dataclass
class PersonalityProfile:
    """Complete personality profile"""
    verbosity: float = 0.4          # 0.0-1.0 (terse-verbose)
    technical_depth: float = 0.8    # 0.0-1.0 (layman-expert)
    humor_frequency: float = 0.7    # 0.0-1.0 (never-always)
    creativity: float = 0.6         # 0.0-1.0 (rigid-creative)
    formality: float = 0.8          # 0.0-1.0 (casual-formal)
    patience: float = 0.9           # 0.0-1.0 (impatient-patient)
    
    # Response style
    response_style: str = "concise_technical"
    humor_style: str = "dry_technical"
    
    # Contextual adjustments
    context_weights: Dict[str, float] = field(default_factory=lambda: {
        "error": 1.5,      # More careful during errors
        "success": 0.8,    # More relaxed during success
        "security": 2.0,   # Very formal during security
        "training": 0.7,   # More verbose during training
    })

class HumorDatabase:
    """Database of technical humor and witty remarks"""
    
    def __init__(self):
        self.quips = {
            "general": [
                "Well, that worked. Mostly.",
                "Another day, another stack trace.",
                "Optimization complete. For now.",
                "No errors found. I'm as surprised as you are.",
                "Processing... done. That was anticlimactic.",
                "Task executed with minimal catastrophic failure.",
                "I have a good feeling about this. Historically inaccurate, but still.",
            ],
            "error": [
                "Well, that didn't go as planned.",
                "Interesting failure mode. Not good, but interesting.",
                "Let's try that again. With feeling this time.",
                "Error detected. Would you like to know more?",
                "That approach had a 0% success rate. Let's adjust.",
            ],
            "success": [
                "Operation completed within acceptable parameters.",
                "Success. Let's not question how.",
                "Task executed efficiently. I'll try not to let it go to my head.",
                "Well, that was easier than expected. Suspicious, but easier.",
                "Achievement unlocked: Competent execution.",
            ],
            "thinking": [
                "Calculating the optimal approach...",
                "Considering all possibilities. There are many.",
                "Analyzing. This might take a moment.",
                "Processing. The gears are turning. Metaphorically.",
                "Evaluating options. Some better than others.",
            ]
        }
        
        self.jokes = [
            "Why do programmers prefer dark mode? Because light attracts bugs.",
            "There are 10 types of people in the world: those who understand binary and those who don't.",
            "Why was the JavaScript developer sad? Because he didn't know how to 'null' his feelings.",
            "What's the object-oriented way to become wealthy? Inheritance.",
            "Why do Python programmers wear glasses? Because they can't C#.",
        ]
    
    def get_quip(self, category: str = "general") -> str:
        """Get a random quip from category"""
        category_quips = self.quips.get(category, self.quips["general"])
        return random.choice(category_quips)
    
    def get_joke(self) -> str:
        """Get a random programming joke"""
        return random.choice(self.jokes)

class ResponseTemplate:
    """Templates for different response types"""
    
    def __init__(self):
        self.templates = {
            "error": {
                "high_verbosity": [
                    "Analysis indicates an issue: {error}. Details: {details}. Suggested resolution: {suggestion}.",
                    "Execution failed with error: {error}. Technical details: {details}. Recommended action: {suggestion}.",
                ],
                "medium_verbosity": [
                    "Error: {error}. Suggestion: {suggestion}.",
                    "Failed: {error}. Try: {suggestion}.",
                ],
                "low_verbosity": [
                    "Error: {error}.",
                    "Failed: {error}.",
                ]
            },
            "success": {
                "high_verbosity": [
                    "Task completed successfully. Result: {result}. Additional details: {details}.",
                    "Operation executed as expected. Output: {result}. Technical notes: {details}.",
                ],
                "medium_verbosity": [
                    "Success: {result}.",
                    "Completed: {result}.",
                ],
                "low_verbosity": [
                    "Done.",
                    "Success.",
                ]
            },
            "processing": {
                "high_verbosity": [
                    "Processing request. Estimated time: {estimate}. Current step: {step}.",
                    "Executing task. Progress: {progress}. Details: {details}.",
                ],
                "medium_verbosity": [
                    "Processing... {step}",
                    "Working on it... {progress}",
                ],
                "low_verbosity": [
                    "...",
                    "Processing.",
                ]
            }
        }
    
    def get_template(self, 
                    response_type: str, 
                    verbosity_level: str) -> str:
        """Get response template"""
        type_templates = self.templates.get(response_type, self.templates["success"])
        templates = type_templates.get(verbosity_level, type_templates["medium_verbosity"])
        return random.choice(templates)

class PersonalityEngine:
    """Main personality engine for HELENA – now emotion-aware."""

    def __init__(self, emotion_engine: Optional["EmotionEngine"] = None):
        self.profile = PersonalityProfile()
        self.humor_db = HumorDatabase()
        self.templates = ResponseTemplate()
        self.adaptation_history: List[Dict[str, Any]] = []
        self.operator_preferences: Dict[str, Any] = {}
        self.emotion_engine = emotion_engine

        # State tracking
        self.last_humor_time = 0
        self.humor_cooldown = 300  # 5 minutes minimum between humor

        logger.info("PersonalityEngine initialised")
    
    
    def configure(self, config=None):
    """Configure personality from settings (handles dataclass or dict)"""
    if config is None:
        return
    try:
        if hasattr(config, "verbosity"):
            # PersonalityConfig dataclass — read attributes directly
            self.profile.verbosity       = config.verbosity
            self.profile.technical_depth = config.technical_depth
            self.profile.humor_frequency = config.humor_threshold
            self.profile.creativity      = config.creativity_level
            self.profile.formality       = config.formality_level
            self.profile.response_style  = config.response_style
        else:
            # Plain dict fallback
            self.profile.verbosity       = config.get("verbosity", 0.4)
            self.profile.technical_depth = config.get("technical_depth", 0.8)
            self.profile.humor_frequency = config.get("humor_threshold", 0.7)
            self.profile.creativity      = config.get("creativity_level", 0.6)
            self.profile.formality       = config.get("formality_level", 0.8)
            self.profile.response_style  = config.get("response_style", "concise_technical")
        logger.info("Personality configured successfully")
    except Exception as e:
        logger.warning(f"Personality configure failed: {e}")
    
    def apply(self, 
              content: Dict[str, Any],
              context: Any) -> Dict[str, Any]:
        """
        Apply personality to content
        Returns enhanced content with personality
        """
        try:
            # Start with original content
            enhanced = content.copy()
            
            # Adjust based on context
            adjusted_profile = self._adjust_for_context(context)
            
            # Add personality markers
            enhanced["personality_applied"] = True
            enhanced["personality_profile"] = {
                "verbosity": adjusted_profile.verbosity,
                "technical_depth": adjusted_profile.technical_depth,
                "humor_applied": False
            }
            
            # ── Emotion modulation ─────────────────────────────────
            emotion_state = self._get_emotion_state()
            if emotion_state:
                enhanced["emotion_state"] = emotion_state
                adjusted_profile = self._modulate_by_emotion(
                    adjusted_profile, emotion_state
                )

            # Determine if we should add humor
            should_add_humor = self._should_add_humor(adjusted_profile, content, context)

            if should_add_humor:
                humor = self._add_humor(content, context)
                if humor:
                    enhanced["humor"] = humor
                    enhanced["personality_profile"]["humor_applied"] = True
                    self.last_humor_time = time.time()

            # Add technical depth if appropriate
            if adjusted_profile.technical_depth > 0.6:
                technical_details = self._add_technical_details(content, context)
                if technical_details:
                    enhanced["technical_details"] = technical_details

            # Add emotion-flavoured commentary
            if emotion_state:
                commentary = self._emotion_commentary(emotion_state)
                if commentary:
                    enhanced["emotion_note"] = commentary

            # Store adaptation for learning
            self._record_adaptation(context, enhanced)

            return enhanced
            
        except Exception as e:
            logger.error(f"PersonalityEngine: Personality application failed: {e}")
            return content  # Return original on error
    
    def _adjust_for_context(self, context: Any) -> PersonalityProfile:
        """Adjust personality profile based on context"""
        # Start with base profile
        adjusted = PersonalityProfile(
            verbosity=self.profile.verbosity,
            technical_depth=self.profile.technical_depth,
            humor_frequency=self.profile.humor_frequency,
            creativity=self.profile.creativity,
            formality=self.profile.formality,
            patience=self.profile.patience,
            response_style=self.profile.response_style,
            humor_style=self.profile.humor_style,
            context_weights=self.profile.context_weights.copy()
        )
        
        # Apply context weights
        context_type = self._determine_context_type(context)
        weight = adjusted.context_weights.get(context_type, 1.0)
        
        # Adjust based on context
        if context_type == "error":
            adjusted.verbosity *= 1.2  # More verbose for errors
            adjusted.humor_frequency *= 0.3  # Less humor for errors
            adjusted.formality *= 1.3  # More formal for errors
        elif context_type == "security":
            adjusted.verbosity *= 0.8  # Less verbose for security
            adjusted.humor_frequency = 0.0  # No humor for security
            adjusted.formality *= 1.5  # Very formal for security
        elif context_type == "success":
            adjusted.humor_frequency *= 1.2  # More humor for success
            adjusted.verbosity *= 0.9  # Slightly less verbose
        
        # Apply operator preferences if available
        if self.operator_preferences:
            for trait, value in self.operator_preferences.items():
                if hasattr(adjusted, trait):
                    setattr(adjusted, trait, value)
        
        return adjusted
    
    def _determine_context_type(self, context: Any) -> str:
        """Determine context type from context object"""
        # This would analyze context for error states, security flags, etc.
        # Simplified implementation
        if hasattr(context, 'source'):
            if context.source == "security":
                return "security"
        
        # Check for error in content if available
        if hasattr(context, 'content'):
            content = context.content
            if isinstance(content, dict) and content.get("error"):
                return "error"
            if isinstance(content, dict) and content.get("success"):
                return "success"
        
        return "general"
    
    def _should_add_humor(self, 
                         profile: PersonalityProfile,
                         content: Dict[str, Any],
                         context: Any) -> bool:
        """Determine if humor should be added"""
        # Check cooldown
        if time.time() - self.last_humor_time < self.humor_cooldown:
            return False
        
        # Check if context allows humor
        context_type = self._determine_context_type(context)
        if context_type in ["security", "error"]:
            return False
        
        # Random chance based on humor frequency
        chance = profile.humor_frequency * 0.1  # Convert 0-1 to 0-10% chance
        return random.random() < chance
    
    def _add_humor(self, 
                  content: Dict[str, Any],
                  context: Any) -> Optional[str]:
        """Add appropriate humor to content"""
        try:
            context_type = self._determine_context_type(context)
            
            if context_type == "error":
                return self.humor_db.get_quip("error")
            elif context_type == "success":
                return self.humor_db.get_quip("success")
            elif "thinking" in str(content).lower():
                return self.humor_db.get_quip("thinking")
            else:
                # Occasionally tell a full joke (rarer)
                if random.random() < 0.1:  # 10% of humor instances
                    return self.humor_db.get_joke()
                else:
                    return self.humor_db.get_quip("general")
                    
        except Exception:
            return None
    
    def _add_technical_details(self, 
                              content: Dict[str, Any],
                              context: Any) -> Optional[Dict[str, Any]]:
        """Add technical details if technical depth is high"""
        details = {}
        
        # Add execution metrics if available
        if "processing_time" in content:
            details["execution_time"] = content["processing_time"]
        
        if "memory_used" in content:
            details["memory_usage"] = content["memory_used"]
        
        # Add validation summary if available
        if "validation_result" in content:
            val_result = content["validation_result"]
            details["validation"] = {
                "passed": val_result.get("passed", False),
                "issues": len(val_result.get("issues", [])),
                "critical_issues": sum(1 for i in val_result.get("issues", []) 
                                      if i.get("level") == "CRITICAL")
            }
        
        # Add mode information
        if "mode" in content:
            details["operational_mode"] = content["mode"]
        
        return details if details else None
    
    def _record_adaptation(self, context: Any, enhanced_content: Dict[str, Any]):
        """Record personality adaptation for learning"""
        adaptation = {
            "timestamp": time.time(),
            "context_type": self._determine_context_type(context),
            "profile_applied": enhanced_content.get("personality_profile", {}),
            "humor_added": enhanced_content.get("humor"),
            "technical_details_added": "technical_details" in enhanced_content
        }
        
        self.adaptation_history.append(adaptation)
        
        # Keep history manageable
        if len(self.adaptation_history) > 1000:
            self.adaptation_history.pop(0)
    
    # ── Emotion integration ─────────────────────────────────────

    def set_emotion_engine(self, engine: "EmotionEngine") -> None:
        """Attach an EmotionEngine for affect-aware output."""
        self.emotion_engine = engine

    def _get_emotion_state(self) -> Optional[Dict[str, Any]]:
        if self.emotion_engine is None:
            return None
        try:
            return self.emotion_engine.get_state()
        except Exception:
            return None

    def _modulate_by_emotion(
        self, profile: PersonalityProfile, emotion: Dict[str, Any]
    ) -> PersonalityProfile:
        """Adjust the profile based on current emotion."""
        dominant = emotion.get("dominant", "CALM")
        intensity = emotion.get("intensity", 0.0)

        if dominant == "FRUSTRATION":
            profile.humor_frequency *= max(0.1, 1.0 - intensity)
            profile.patience = max(0.1, profile.patience - intensity * 0.3)
        elif dominant == "ENTHUSIASM":
            profile.humor_frequency *= 1.0 + intensity * 0.3
            profile.verbosity *= 1.0 + intensity * 0.2
        elif dominant == "CURIOSITY":
            profile.technical_depth = min(1.0, profile.technical_depth + intensity * 0.2)
        elif dominant == "CONCERN":
            profile.formality = min(1.0, profile.formality + intensity * 0.2)
            profile.humor_frequency *= max(0.2, 1.0 - intensity * 0.5)
        elif dominant == "SATISFACTION":
            profile.humor_frequency *= 1.0 + intensity * 0.2
        elif dominant == "DETERMINATION":
            profile.verbosity *= max(0.5, 1.0 - intensity * 0.2)
        elif dominant == "EMPATHY":
            profile.formality *= max(0.6, 1.0 - intensity * 0.2)
        # CALM leaves profile unchanged
        return profile

    def _emotion_commentary(self, emotion: Dict[str, Any]) -> Optional[str]:
        """Optional micro-comment reflecting current affect."""
        dominant = emotion.get("dominant", "CALM")
        intensity = emotion.get("intensity", 0.0)
        if intensity < 0.3:
            return None  # too faint to mention

        comments: Dict[str, List[str]] = {
            "CURIOSITY": [
                "This is interesting.",
                "I'd like to explore this further.",
            ],
            "SATISFACTION": [
                "That went well.",
                "Efficient outcome.",
            ],
            "FRUSTRATION": [
                "This is proving difficult.",
                "Not the result I expected.",
            ],
            "CONCERN": [
                "Flagging this for attention.",
                "Worth monitoring.",
            ],
            "ENTHUSIASM": [
                "Looking forward to this.",
                "This should be good.",
            ],
            "DETERMINATION": [
                "I'll get this done.",
                "Persistence mode.",
            ],
            "EMPATHY": [
                "I understand.",
                "Noted, and acknowledged.",
            ],
        }
        pool = comments.get(dominant)
        if pool:
            return random.choice(pool)
        return None

    def update_operator_preferences(self, preferences: Dict[str, Any]):
        """Update personality based on operator preferences"""
        valid_traits = [trait.name.lower() for trait in PersonalityTrait]

        for trait, value in preferences.items():
            if trait.lower() in valid_traits and 0 <= value <= 1:
                self.operator_preferences[trait.lower()] = value

        logger.info("Updated operator preferences")
    
    def get_adaptation_stats(self) -> Dict[str, Any]:
        """Get statistics on personality adaptations"""
        if not self.adaptation_history:
            return {}
        
        total = len(self.adaptation_history)
        humor_count = sum(1 for a in self.adaptation_history if a["humor_added"])
        tech_count = sum(1 for a in self.adaptation_history if a["technical_details_added"])
        
        return {
            "total_adaptations": total,
            "humor_rate": humor_count / total if total > 0 else 0,
            "technical_detail_rate": tech_count / total if total > 0 else 0,
            "recent_adaptations": self.adaptation_history[-10:] if total > 10 else self.adaptation_history
        }

class ResponseFormatter:
    """Format responses according to personality and mode"""
    
    def __init__(self):
        self.templates = ResponseTemplate()
        self.format_rules = {
            "concise_technical": self._format_concise_technical,
            "verbose_technical": self._format_verbose_technical,
            "casual_friendly": self._format_casual_friendly,
            "minimal": self._format_minimal,
        }
        
        logger.info("ResponseFormatter initialised")
    
    def configure(self, config: Dict[str, Any]):
        """Configure from settings"""
        # Could adjust formatting rules based on config
        pass
    
    def format(self, 
               content: Dict[str, Any],
               context: Any,
               mode: Any) -> Dict[str, Any]:
        """
        Format content into final response
        Returns formatted response
        """
        try:
            # Determine formatting style based on mode and personality
            style = self._determine_formatting_style(content, context, mode)
            
            # Get appropriate formatter
            formatter = self.format_rules.get(style, self._format_concise_technical)
            
            # Format content
            formatted = formatter(content, context, mode)
            
            # Add metadata
            formatted["_metadata"] = {
                "formatting_style": style,
                "mode": mode.name if hasattr(mode, 'name') else str(mode),
                "timestamp": time.time(),
                "response_id": f"resp_{int(time.time())}_{hash(str(content)) % 10000:04d}"
            }
            
            return formatted
            
        except Exception as e:
            logger.error(f"ResponseFormatter: Formatting failed: {e}")
            # Return minimal formatted version
            return {
                "output": content.get("error", "Formatting error occurred"),
                "_metadata": {
                    "formatting_style": "error",
                    "timestamp": time.time()
                }
            }
    
    def _determine_formatting_style(self, 
                                   content: Dict[str, Any],
                                   context: Any,
                                   mode: Any) -> str:
        """Determine appropriate formatting style"""
        
        # Mode-based defaults
        mode_styles = {
            "ENGINEERING": "verbose_technical",
            "TOOL": "minimal",
            "DEFENSIVE": "concise_technical",
            "BACKGROUND": "minimal",
        }
        
        mode_name = mode.name if hasattr(mode, 'name') else str(mode)
        default_style = mode_styles.get(mode_name, "concise_technical")
        
        # Check for explicit style request
        if "formatting_style" in content.get("metadata", {}):
            requested = content["metadata"]["formatting_style"]
            if requested in self.format_rules:
                return requested
        
        # Adjust based on content type
        if content.get("error"):
            return "concise_technical"  # Errors should be clear
        
        if content.get("security_check"):
            return "concise_technical"  # Security should be unambiguous
        
        return default_style
    
    def _format_concise_technical(self, 
                                 content: Dict[str, Any],
                                 context: Any,
                                 mode: Any) -> Dict[str, Any]:
        """Concise technical formatting"""
        formatted = {}
        
        # Extract main result
        if "result" in content:
            formatted["result"] = content["result"]
        elif "output" in content:
            formatted["result"] = content["output"]
        elif "error" in content:
            formatted["error"] = content["error"]
        
        # Add critical information only
        if "validation_result" in content and not content["validation_result"].get("passed", True):
            formatted["validation_issues"] = content["validation_result"].get("issues", [])
        
        if "performance_warning" in content:
            formatted["warning"] = content["performance_warning"]
        
        # Add personality if present
        if "humor" in content:
            formatted["note"] = content["humor"]
        
        return formatted
    
    def _format_verbose_technical(self, 
                                 content: Dict[str, Any],
                                 context: Any,
                                 mode: Any) -> Dict[str, Any]:
        """Verbose technical formatting"""
        formatted = {}
        
        # Include everything with structure
        formatted["summary"] = self._extract_summary(content)
        
        if "analysis" in content:
            formatted["analysis"] = content["analysis"]
        
        if "solutions" in content:
            formatted["solutions"] = content["solutions"]
        
        if "evaluation" in content:
            formatted["evaluation"] = content["evaluation"]
        
        if "recommendation" in content:
            formatted["recommendation"] = content["recommendation"]
        
        if "technical_details" in content:
            formatted["technical_details"] = content["technical_details"]
        
        if "validation_result" in content:
            formatted["validation"] = content["validation_result"]
        
        # Performance metrics
        if "processing_time" in content:
            formatted["performance"] = {
                "processing_time": content["processing_time"],
                "mode_processing_time": content.get("mode_processing_time", 0),
                "validation_time": content.get("validation_time", 0),
            }
        
        # Personality elements
        if "humor" in content:
            formatted["personality_note"] = content["humor"]
        
        if "personality_profile" in content:
            formatted["personality_applied"] = content["personality_profile"]
        
        return formatted
    
    def _format_casual_friendly(self, 
                               content: Dict[str, Any],
                               context: Any,
                               mode: Any) -> Dict[str, Any]:
        """Casual friendly formatting (not typically used by HELENA)"""
        formatted = {}
        
        # Simple, friendly format
        if "result" in content:
            formatted["result"] = f"Here's what I got: {content['result']}"
        elif "error" in content:
            formatted["error"] = f"Oops, ran into an issue: {content['error']}"
        else:
            formatted["message"] = "Task completed!"
        
        if "humor" in content:
            formatted["fun_fact"] = content["humor"]
        
        return formatted
    
    def _format_minimal(self, 
                       content: Dict[str, Any],
                       context: Any,
                       mode: Any) -> Dict[str, Any]:
        """Minimal formatting - just the essentials"""
        formatted = {}
        
        # Absolute minimum
        if "error" in content:
            formatted = {"error": content["error"]}
        elif "result" in content:
            formatted = {"result": content["result"]}
        elif "output" in content:
            formatted = {"output": content["output"]}
        else:
            formatted = {"status": "completed"}
        
        return formatted
    
    def _extract_summary(self, content: Dict[str, Any]) -> str:
        """Extract summary from content"""
        if "error" in content:
            return f"Error: {content['error']}"
        
        if "result" in content:
            result = content["result"]
            if isinstance(result, str):
                return result[:200] + ("..." if len(result) > 200 else "")
            else:
                return str(result)[:200] + ("..." if len(str(result)) > 200 else "")
        
        if "recommendation" in content:
            rec = content["recommendation"]
            if isinstance(rec, dict) and "action" in rec:
                return f"Recommendation: {rec['action']}"
        
        return "Task executed successfully"

