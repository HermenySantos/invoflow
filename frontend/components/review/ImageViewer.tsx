'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { 
  ZoomIn, 
  ZoomOut, 
  Maximize2, 
  Minimize2, 
  X,
  FileText,
  Loader2
} from 'lucide-react';

interface ImageViewerProps {
  src: string | null;
  alt?: string;
  mimeType?: string;
  filename?: string;
  className?: string;
}

const ZOOM_LEVELS = [1, 1.5, 2, 2.5, 3];
const MIN_ZOOM = 0;
const MAX_ZOOM = ZOOM_LEVELS.length - 1;

export function ImageViewer({ 
  src, 
  alt = 'Document preview',
  mimeType,
  filename,
  className = ''
}: ImageViewerProps) {
  const [zoomIndex, setZoomIndex] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  
  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const lastTouchDistance = useRef<number | null>(null);

  const zoom = ZOOM_LEVELS[zoomIndex];
  const isPdf = mimeType?.includes('pdf');

  // Reset state when src changes
  useEffect(() => {
    setIsLoading(true);
    setHasError(false);
    setZoomIndex(0);
    setPosition({ x: 0, y: 0 });
  }, [src]);

  const handleZoomIn = useCallback(() => {
    setZoomIndex(prev => Math.min(prev + 1, MAX_ZOOM));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoomIndex(prev => Math.max(prev - 1, MIN_ZOOM));
    // Reset position when zooming out to prevent image being out of view
    if (zoomIndex <= 1) {
      setPosition({ x: 0, y: 0 });
    }
  }, [zoomIndex]);

  const handleDoubleClick = useCallback(() => {
    if (zoomIndex === 0) {
      setZoomIndex(2); // Jump to 2x zoom
    } else {
      setZoomIndex(0);
      setPosition({ x: 0, y: 0 });
    }
  }, [zoomIndex]);

  const toggleFullscreen = useCallback(() => {
    setIsFullscreen(prev => !prev);
    if (isFullscreen) {
      // Reset zoom when exiting fullscreen
      setZoomIndex(0);
      setPosition({ x: 0, y: 0 });
    }
  }, [isFullscreen]);

  // Mouse drag handling for panning when zoomed
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (zoom > 1) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
    }
  }, [zoom, position]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (isDragging && zoom > 1) {
      setPosition({
        x: e.clientX - dragStart.x,
        y: e.clientY - dragStart.y
      });
    }
  }, [isDragging, zoom, dragStart]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Touch handling for pinch-to-zoom
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2) {
      const distance = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      lastTouchDistance.current = distance;
    } else if (e.touches.length === 1 && zoom > 1) {
      setIsDragging(true);
      setDragStart({ 
        x: e.touches[0].clientX - position.x, 
        y: e.touches[0].clientY - position.y 
      });
    }
  }, [zoom, position]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (e.touches.length === 2 && lastTouchDistance.current !== null) {
      e.preventDefault();
      const distance = Math.hypot(
        e.touches[0].clientX - e.touches[1].clientX,
        e.touches[0].clientY - e.touches[1].clientY
      );
      const delta = distance - lastTouchDistance.current;
      
      if (Math.abs(delta) > 10) {
        if (delta > 0) {
          setZoomIndex(prev => Math.min(prev + 1, MAX_ZOOM));
        } else {
          setZoomIndex(prev => Math.max(prev - 1, MIN_ZOOM));
        }
        lastTouchDistance.current = distance;
      }
    } else if (e.touches.length === 1 && isDragging && zoom > 1) {
      setPosition({
        x: e.touches[0].clientX - dragStart.x,
        y: e.touches[0].clientY - dragStart.y
      });
    }
  }, [isDragging, zoom, dragStart]);

  const handleTouchEnd = useCallback(() => {
    lastTouchDistance.current = null;
    setIsDragging(false);
  }, []);

  // Keyboard zoom controls
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isFullscreen) return;
      
      if (e.key === '+' || e.key === '=') {
        handleZoomIn();
      } else if (e.key === '-') {
        handleZoomOut();
      } else if (e.key === 'Escape') {
        setIsFullscreen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isFullscreen, handleZoomIn, handleZoomOut]);

  const handleImageLoad = () => {
    setIsLoading(false);
    setHasError(false);
  };

  const handleImageError = () => {
    setIsLoading(false);
    setHasError(true);
  };

  // PDF placeholder
  if (isPdf) {
    return (
      <div className={`relative bg-gray-100 rounded-xl flex flex-col items-center justify-center p-8 ${className}`}>
        <FileText className="w-16 h-16 text-gray-400 mb-3" />
        <p className="text-sm font-medium text-gray-700">{filename || 'PDF Document'}</p>
        <p className="text-xs text-gray-500 mt-1">PDF preview not available</p>
        {src && (
          <a 
            href={src} 
            target="_blank" 
            rel="noopener noreferrer"
            className="mt-4 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors"
          >
            Open PDF
          </a>
        )}
      </div>
    );
  }

  // No image placeholder
  if (!src) {
    return (
      <div className={`relative bg-gray-100 rounded-xl flex flex-col items-center justify-center p-8 ${className}`}>
        <FileText className="w-16 h-16 text-gray-300 mb-3" />
        <p className="text-sm text-gray-500">No image available</p>
      </div>
    );
  }

  const imageContent = (
    <div
      ref={containerRef}
      className={`relative overflow-hidden ${isFullscreen ? 'w-full h-full' : 'rounded-xl'} ${className}`}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onDoubleClick={handleDoubleClick}
      style={{ cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'zoom-in' }}
    >
      {/* Loading skeleton */}
      {isLoading && (
        <div className="absolute inset-0 bg-gray-200 animate-pulse flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-gray-400 animate-spin" />
        </div>
      )}

      {/* Error state */}
      {hasError && (
        <div className="absolute inset-0 bg-gray-100 flex flex-col items-center justify-center">
          <FileText className="w-12 h-12 text-gray-400 mb-2" />
          <p className="text-sm text-gray-500">Failed to load image</p>
        </div>
      )}

      {/* Image */}
      <img
        ref={imageRef}
        src={src}
        alt={alt}
        onLoad={handleImageLoad}
        onError={handleImageError}
        className={`w-full h-full object-contain transition-transform duration-200 ${isLoading || hasError ? 'invisible' : ''}`}
        style={{
          transform: `scale(${zoom}) translate(${position.x / zoom}px, ${position.y / zoom}px)`,
          transformOrigin: 'center center',
        }}
        draggable={false}
      />

      {/* Zoom controls */}
      <div className="absolute bottom-3 right-3 flex items-center gap-1 bg-black/60 backdrop-blur-sm rounded-lg p-1">
        <button
          onClick={(e) => { e.stopPropagation(); handleZoomOut(); }}
          disabled={zoomIndex === MIN_ZOOM}
          className="p-1.5 text-white hover:bg-white/20 rounded disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          aria-label="Zoom out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        
        <span className="text-white text-xs font-medium px-2 min-w-[3rem] text-center">
          {Math.round(zoom * 100)}%
        </span>
        
        <button
          onClick={(e) => { e.stopPropagation(); handleZoomIn(); }}
          disabled={zoomIndex === MAX_ZOOM}
          className="p-1.5 text-white hover:bg-white/20 rounded disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          aria-label="Zoom in"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <div className="w-px h-4 bg-white/30 mx-1" />

        <button
          onClick={(e) => { e.stopPropagation(); toggleFullscreen(); }}
          className="p-1.5 text-white hover:bg-white/20 rounded transition-colors"
          aria-label={isFullscreen ? 'Exit fullscreen' : 'View fullscreen'}
        >
          {isFullscreen ? (
            <Minimize2 className="w-4 h-4" />
          ) : (
            <Maximize2 className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Tap to expand hint on mobile */}
      {!isFullscreen && zoom === 1 && (
        <div className="absolute bottom-3 left-3 text-xs text-white bg-black/50 backdrop-blur-sm px-2 py-1 rounded-md lg:hidden pointer-events-none">
          Tap to expand
        </div>
      )}
    </div>
  );

  // Fullscreen modal
  if (isFullscreen) {
    return (
      <div className="fixed inset-0 z-[100] bg-black flex items-center justify-center">
        {/* Close button */}
        <button
          onClick={toggleFullscreen}
          className="absolute top-4 right-4 z-10 p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors"
          aria-label="Close fullscreen"
        >
          <X className="w-6 h-6" />
        </button>

        {/* Filename */}
        {filename && (
          <div className="absolute top-4 left-4 text-white text-sm bg-black/50 backdrop-blur-sm px-3 py-1.5 rounded-lg">
            {filename}
          </div>
        )}

        {imageContent}
      </div>
    );
  }

  return imageContent;
}

export default ImageViewer;
