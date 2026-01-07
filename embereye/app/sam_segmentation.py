"""
FastSAM integration for click-to-segment annotation in EmberEye.
Provides lightweight AI-powered segmentation for annotation tool.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
import logging
import importlib

logger = logging.getLogger(__name__)


class SAMSegmenter:
    """FastSAM-based segmentation helper for annotation tool."""
    
    def __init__(self):
        self.model = None
        self.current_frame = None
        # Default to CPU; attempt CUDA only if torch is available and working
        self.device = 'cpu'
        try:
            try:
                _torch = importlib.import_module('torch')
                if _torch is not None:
                    cuda_attr = getattr(_torch, 'cuda', None)
                    if cuda_attr is not None:
                        is_available = getattr(cuda_attr, 'is_available', None)
                        if is_available is not None and callable(is_available):
                            if is_available():
                                self.device = 'cuda'
            except (ImportError, AttributeError, OSError) as e:
                # torch DLL load error, CUDA unavailable, or attribute missing - all OK
                logger.debug(f"CUDA not available: {type(e).__name__}: {e}")
        except Exception:
            # Catch-all for any unexpected torch issues; keep CPU
            self.device = 'cpu'
        self.use_grabcut_fallback = True  # Enable GrabCut fallback
        logger.info(f"SAM Segmenter initialized on device: {self.device}")
    
    def load_model(self):
        """Lazy load FastSAM model on first use."""
        if self.model is not None:
            return True
        
        try:
            # Import FastSAM from ultralytics dynamically to avoid build-time import issues
            logger.info("Attempting to import FastSAM...")
            ul = importlib.import_module('ultralytics')
            FastSAM = getattr(ul, 'FastSAM', None)
            if FastSAM is None:
                raise ImportError('FastSAM not found in ultralytics')

            logger.info("Loading FastSAM-s model (small, ~23MB)...")
            self.model = FastSAM('FastSAM-s.pt')
            logger.info("✓ FastSAM model loaded successfully on device: " + self.device)
            return True

        except Exception as e:
            logger.error(f"✗ Failed to load FastSAM model: {e}")
            logger.info("Will use GrabCut fallback instead (still works well)")
            return False
    
    def set_frame(self, frame_bgr: np.ndarray):
        """Set the current frame for segmentation."""
        self.current_frame = frame_bgr.copy()
    
    def segment_at_point(self, x: int, y: int, frame_width: int, frame_height: int) -> Optional[List[Tuple[float, float]]]:
        """
        Generate segmentation mask at click point and return polygon coordinates.
        
        Args:
            x, y: Click coordinates in display space
            frame_width, frame_height: Display dimensions
        
        Returns:
            List of (x, y) normalized polygon points [0-1], or None if failed
        """
        if self.current_frame is None:
            logger.warning("No frame set for segmentation")
            return None
        
        # Try to load FastSAM model (will use GrabCut if loading fails)
        fastsam_available = self.load_model()
        
        if not fastsam_available:
            logger.info("FastSAM not available, using GrabCut fallback directly")
            h, w = self.current_frame.shape[:2]
            scale_x = w / frame_width
            scale_y = h / frame_height
            orig_x = int(x * scale_x)
            orig_y = int(y * scale_y)
            return self._grabcut_segment(orig_x, orig_y, w, h)
        
        try:
            # Get original image dimensions
            h, w = self.current_frame.shape[:2]
            scale_x = w / frame_width
            scale_y = h / frame_height
            
            # Convert click to original image coordinates
            orig_x = int(x * scale_x)
            orig_y = int(y * scale_y)
            
            logger.info(f"Segmenting at display ({x},{y}) -> original ({orig_x},{orig_y})")
            
            # Run FastSAM inference on entire image
            logger.info("Running FastSAM inference...")
            results = self.model(
                self.current_frame,
                device=self.device,
                retina_masks=True,
                imgsz=640,
                conf=0.25,  # Lower confidence to get more masks
                iou=0.7,
            )
            
            if not results or len(results) == 0:
                logger.warning("No segmentation results from FastSAM, trying GrabCut fallback")
                if self.use_grabcut_fallback:
                    return self._grabcut_segment(orig_x, orig_y, w, h)
                return None
            
            # Get masks from results
            masks = results[0].masks
            if masks is None or len(masks.data) == 0:
                logger.warning("No masks found in FastSAM results, trying GrabCut fallback")
                if self.use_grabcut_fallback:
                    return self._grabcut_segment(orig_x, orig_y, w, h)
                return None
            
            logger.info(f"FastSAM generated {len(masks.data)} masks")
            
            # Find mask containing click point
            best_mask = None
            best_mask_idx = -1
            min_distance = float('inf')
            
            for idx, mask in enumerate(masks.data):
                mask_np = mask.cpu().numpy()
                
                # Resize mask to original image size if needed
                if len(mask_np.shape) == 3:
                    mask_np = mask_np[0]  # Remove batch dimension
                    
                if mask_np.shape[:2] != (h, w):
                    mask_np = cv2.resize(mask_np, (w, h), interpolation=cv2.INTER_NEAREST)
                
                # Check if click point is inside mask
                if 0 <= orig_y < mask_np.shape[0] and 0 <= orig_x < mask_np.shape[1]:
                    if mask_np[orig_y, orig_x] > 0.3:
                        # Found mask at click point
                        best_mask = mask_np
                        best_mask_idx = idx
                        logger.info(f"Found mask #{idx} at click point")
                        break
                    
                    # Calculate distance to nearest mask pixel for fallback
                    mask_pixels = np.argwhere(mask_np > 0.3)
                    if len(mask_pixels) > 0:
                        distances = np.sqrt(((mask_pixels - np.array([orig_y, orig_x])) ** 2).sum(axis=1))
                        min_dist = distances.min()
                        if min_dist < min_distance:
                            min_distance = min_dist
                            best_mask = mask_np
                            best_mask_idx = idx
            
            if best_mask is None:
                logger.warning("No mask found near click point, trying GrabCut fallback")
                if self.use_grabcut_fallback:
                    return self._grabcut_segment(orig_x, orig_y, w, h)
                return None
            
            logger.info(f"Using mask #{best_mask_idx} (distance: {min_distance:.1f}px)")
            
            # Convert mask to polygon
            polygon = self._mask_to_polygon(best_mask)
            
            if polygon is None or len(polygon) < 3:
                logger.warning("Failed to extract polygon from mask")
                return None
            
            # Normalize polygon coordinates to [0-1]
            h, w = self.current_frame.shape[:2]
            normalized_polygon = []
            for px, py in polygon:
                norm_x = px / w
                norm_y = py / h
                normalized_polygon.append((norm_x, norm_y))
            
            logger.info(f"Generated polygon with {len(normalized_polygon)} points")
            return normalized_polygon
            
        except Exception as e:
            logger.error(f"Segmentation failed: {e}", exc_info=True)
            return None
    
    def _grabcut_segment(self, x: int, y: int, w: int, h: int) -> Optional[List[Tuple[float, float]]]:
        """
        Simple GrabCut-based segmentation around click point.
        Used as fallback when FastSAM fails.
        
        Args:
            x, y: Click coordinates in original image space
            w, h: Image dimensions
        
        Returns:
            Normalized polygon points or None
        """
        try:
            logger.info(f"Using GrabCut segmentation fallback at ({x}, {y}) in frame {w}x{h}")
            
            # Validate click coordinates
            if x < 0 or x >= w or y < 0 or y >= h:
                logger.error(f"Click coordinates ({x}, {y}) out of bounds for frame {w}x{h}")
                return None
            
            # Define rectangular region around click (50-pixel margin = 100x100 region)
            # Smaller region reduces interference from background objects
            margin = 50
            rect_x = max(0, x - margin)
            rect_y = max(0, y - margin)
            rect_w = min(2 * margin, w - rect_x)
            rect_h = min(2 * margin, h - rect_y)
            
            # Ensure minimum size for GrabCut to work effectively
            min_size = 50
            if rect_w < min_size or rect_h < min_size:
                logger.warning(f"Region too small for GrabCut: {rect_w}x{rect_h} (need {min_size}x{min_size})")
                # Try expanding in opposite direction if near edge
                if rect_w < min_size:
                    rect_x = max(0, min(rect_x, w - min_size))
                    rect_w = min(min_size, w - rect_x)
                if rect_h < min_size:
                    rect_y = max(0, min(rect_y, h - min_size))
                    rect_h = min(min_size, h - rect_y)
                
                # If still too small, give up
                if rect_w < min_size or rect_h < min_size:
                    logger.error(f"Cannot create valid GrabCut region: final size {rect_w}x{rect_h}")
                    return None
            
            logger.info(f"GrabCut rect: x={rect_x}, y={rect_y}, w={rect_w}, h={rect_h}")
            
            # Initialize mask and models
            mask = np.zeros(self.current_frame.shape[:2], np.uint8)
            bgd_model = np.zeros((1, 65), np.float64)
            fgd_model = np.zeros((1, 65), np.float64)
            
            # Strategy: Set everything to probable background first, then mark foreground
            # This constrains GrabCut to work within the rect region only
            mask[:, :] = cv2.GC_BGD  # Everything is background by default
            
            # Mark the rect region as probably background (will refine)
            mask[rect_y:rect_y+rect_h, rect_x:rect_x+rect_w] = cv2.GC_PR_BGD
            
            # Mark click point area as definitely foreground with LARGE radius
            # This forces GrabCut to include the clicked object, not background machinery
            cv2.circle(mask, (x, y), 40, cv2.GC_FGD, -1)
            
            # No probable foreground layer - keep it simple and strong
            
            logger.info(f"GrabCut mask setup: Strong FG circle r=40px at ({x},{y}), search region {rect_w}x{rect_h}")
            logger.info("Running GrabCut algorithm with 10 iterations...")
            # Run GrabCut with mask-based initialization (seed points)
            cv2.grabCut(self.current_frame, mask, None, bgd_model, fgd_model, 10, cv2.GC_INIT_WITH_MASK)
            
            # Create binary mask - include both definite and probable foreground
            binary_mask = np.where((mask == 1) | (mask == 3), 1, 0).astype('uint8')
            foreground_count = np.sum(binary_mask > 0)
            logger.info(f"GrabCut mask with seed points: {foreground_count} foreground pixels")
            
            # Accept GrabCut results if reasonable (even small ones)
            # GrabCut is just a fallback - FastSAM would work much better
            if foreground_count < 500:
                logger.warning(f"⚠️  GrabCut segmentation quality is poor ({foreground_count} pixels)")
                logger.warning("⚠️  For better AI segmentation, install FastSAM:")
                logger.warning("⚠️  pip install --upgrade ultralytics>=8.1.0")
                logger.warning("⚠️  Or use Rectangle mode for more accurate annotations")
            
            # Only fall back to circle if completely failed
            if foreground_count < 200:
                logger.info(f"GrabCut found too few pixels ({foreground_count}), using circle fallback...")
                binary_mask = np.zeros(self.current_frame.shape[:2], np.uint8)
                # Draw larger circle to better cover objects
                cv2.circle(binary_mask, (x, y), 50, 1, -1)
                foreground_count = np.sum(binary_mask > 0)
                logger.info(f"Circle fallback: {foreground_count} foreground pixels")
            
            # Convert to polygon
            polygon = self._mask_to_polygon(binary_mask)
            
            if polygon is None or len(polygon) < 3:
                logger.warning("GrabCut failed to generate valid polygon")
                return None
            
            # Normalize coordinates
            normalized_polygon = []
            for px, py in polygon:
                normalized_polygon.append((px / w, py / h))
            
            logger.info(f"GrabCut generated polygon with {len(normalized_polygon)} points")
            return normalized_polygon
            
        except Exception as e:
            logger.error(f"GrabCut segmentation failed: {e}", exc_info=True)
            return None
    
    def _mask_to_polygon(self, mask: np.ndarray, epsilon_factor: float = 0.002) -> Optional[List[Tuple[int, int]]]:
        """
        Convert binary mask to polygon contour.
        
        Args:
            mask: Binary mask (HxW)
            epsilon_factor: Contour approximation factor (lower = more points)
        
        Returns:
            List of (x, y) polygon points, or None
        """
        try:
            logger.info(f"Converting mask to polygon, mask shape: {mask.shape}, unique values: {np.unique(mask)}")
            
            # Ensure mask is binary uint8
            mask_uint8 = (mask > 0.5).astype(np.uint8) * 255
            
            logger.info(f"Binary mask has {np.sum(mask_uint8 > 0)} non-zero pixels")
            
            # Find contours
            contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            logger.info(f"Found {len(contours)} contours")
            
            if not contours:
                logger.warning("No contours found in mask")
                return None
            
            # Use largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            
            logger.info(f"Largest contour has area: {area}")
            
            if area < 10:
                logger.warning(f"Contour area too small: {area}")
                return None
            
            # Approximate contour to reduce points
            epsilon = epsilon_factor * cv2.arcLength(largest_contour, True)
            approx = cv2.approxPolyDP(largest_contour, epsilon, True)
            
            # Convert to list of tuples
            polygon = [(int(pt[0][0]), int(pt[0][1])) for pt in approx]
            
            logger.info(f"Polygon has {len(polygon)} points")
            
            # YOLO requires at least 3 points
            if len(polygon) < 3:
                return None
            
            return polygon
            
        except Exception as e:
            logger.error(f"Failed to convert mask to polygon: {e}")
            return None
