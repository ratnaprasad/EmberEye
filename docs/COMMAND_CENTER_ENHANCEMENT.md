# EmberEye Hollywood Command Center Enhancement

## Overview
Transform EmberEye into a professional Hollywood-style command center with video wall aesthetics, reorganized menu system, and Amazon Prime-inspired dropdown interfaces.

## ✅ Phase 1: Dual Theme System (COMPLETED)
- **Status**: ✅ Fully implemented and tested
- **Files**: `theme_manager.py`, `ee_loginwindow.py`, `video_widget.py`
- **Features**:
  - Classic theme (light, traditional UI)
  - Modern theme (dark, video-focused)
  - Login screen theme selection
  - Theme persistence across sessions
  - 600+ lines of modern QSS styling

## 🎯 Phase 2: Hollywood Command Center UI (IN PROGRESS)

### Menu Reorganization
**Status**: Design complete, implementation ready

#### Profile Icon Dropdown (👤)
```
👤 Profile
   ├── 👤 My Profile
   └── 🚪 Logout
```

#### Settings Gear Icon (⚙️)
```
⚙️ Settings
   ├── 🎥 Configure Streams
   ├── 🔄 Reset Streams
   ├──────────────────
   ├── 💾 Backup Configuration
   ├── 📂 Restore Configuration
   ├──────────────────
   ├── 🔌 TCP Server Port
   ├── 🌡 Thermal Grid Settings
   ├── 📊 Numeric Grid (All Streams)
   ├── 🎛 Sensor Configuration
   ├── 📋 Log Viewer
   ├──────────────────
   ├── 🔥 PFDS Devices
   │   ├── ➕ Add Device
   │   └── 👁 View Devices
   ├──────────────────
   └── 🧪 Test Stream Error
```

### Header Design
```
╔════════════════════════════════════════════════════════════════════════════╗
║  🔥 EMBER EYE          VIEW: [All Groups ▼]                    ⚙️  👤    ║
║     COMMAND CENTER                                                         ║
╚════════════════════════════════════════════════════════════════════════════╝
```

**Features**:
- Gradient background (#1a1a1a → #252525 → #1a1a1a)
- Cyan accent border (#00bcd4)
- 70px fixed height for prominent branding
- Logo with "EMBER EYE" and "COMMAND CENTER" subtitle
- Circular icon buttons with hover effects
- Amazon Prime-style dropdown menus

### Tab Layout
```
╔════════════════════════════════════════════════════════════════════════════╗
║ 🎥 VIDEO WALL  |  📊 ANALYTICS  |  🚨 ANOMALIES  |  ⚠️ DEVICES             ║
╠════════════════════════════════════════════════════════════════════════════╣
║                                                                            ║
║  [Video Wall Content]                                                      ║
║                                                                            ║
╚════════════════════════════════════════════════════════════════════════════╝
```

**Tab Styling** (Modern Theme):
- Frameless design (document mode)
- Dark background (#1a1a1a)
- Unselected tabs: #252525, gray text (#9e9e9e)
- Selected tabs: #1a1a1a, cyan text (#00bcd4), cyan top border
- Hover effect: #2d2d2d
- 12px vertical padding, 24px horizontal padding
- Bold, 12px font, 1px letter-spacing

### Video Wall Grid
```
╔══════╦══════╦══════╦══════╗
║ CAM1 ║ CAM2 ║ CAM3 ║ CAM4 ║
╠══════╬══════╬══════╬══════╣
║ CAM5 ║ CAM6 ║ CAM7 ║ CAM8 ║
╠══════╬══════╬══════╬══════╣
║ CAM9 ║ CA10 ║ CA11 ║ CA12 ║
╠══════╬══════╬══════╬══════╣
║ CA13 ║ CA14 ║ CA15 ║ CA16 ║
╚══════╩══════╩══════╩══════╝
```

**Features**:
- Grid options: 2×2, 3×3, 4×4, 5×5
- 2px spacing between tiles (minimal for seamless look)
- Black background (#0a0a0a) for depth
- Slim control bar with modern styling
- Circular navigation buttons (◀ ▶)
- Grid selector with cyan borders

### Control Bar Design
```
┌────────────────────────────────────────────────────────────────┐
│  GRID: [4×4 ▼]                               ◀  Page 1/3  ▶   │
└────────────────────────────────────────────────────────────────┘
```

**Styling**:
- Semi-transparent background (rgba(0, 0, 0, 0.3))
- Border-radius: 6px
- Padding: 12px 8px
- Cyan accent labels (#00bcd4)
- Hover effects on all interactive elements

### Dropdown Menu Style (Amazon Prime Inspired)
```css
QMenu {
    background-color: #2d2d2d;
    border: 1px solid #00bcd4;
    border-radius: 8px;
    padding: 8px 0;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
}
QMenu::item {
    padding: 10px 24px;
    color: #e0e0e0;
    font-size: 13px;
    font-weight: 500;
}
QMenu::item:selected {
    background-color: rgba(0, 188, 212, 0.2);
    color: #00bcd4;
}
```

### Status Bar (Hollywood Style)
```
╔════════════════════════════════════════════════════════════════╗
║  🟢 System Ready  •  TCP: Port 6969  •  Streams: 12/16 Active  ║
╚════════════════════════════════════════════════════════════════╝
```

**Styling**:
- Gradient background matching header
- Cyan text (#00bcd4)
- 1px cyan top border
- Bold, 11px font
- Real-time status indicators

## Implementation Code Snippets

### Header with Dual Icons
```python
def init_header_actions(self, header_layout, is_modern):
    \"\"\"Create Settings gear icon and Profile icon with dropdown overlays\"\"\"
    
    # Settings Gear Icon
    settings_btn = QToolButton()
    settings_btn.setText("⚙")
    settings_btn.setFixedSize(44, 44)
    settings_btn.setPopupMode(QToolButton.InstantPopup)
    settings_btn.setCursor(Qt.PointingHandCursor)
    if is_modern:
        settings_btn.setStyleSheet(\"\"\"
            QToolButton {
                background-color: rgba(0, 188, 212, 0.15);
                border: 1px solid rgba(0, 188, 212, 0.3);
                border-radius: 22px;
                color: #00bcd4;
                font-size: 20px;
                font-weight: bold;
            }
            QToolButton:hover {
                background-color: rgba(0, 188, 212, 0.3);
                border-color: #00bcd4;
            }
            QToolButton::menu-indicator { image: none; }
        \"\"\")
    
    settings_menu = QMenu()
    self._style_dropdown_menu(settings_menu, is_modern)
    # ... add menu items ...
    settings_btn.setMenu(settings_menu)
    header_layout.addWidget(settings_btn)
    
    # Profile Icon (similar implementation)
```

### Amazon Prime Dropdown Styling
```python
def _style_dropdown_menu(self, menu, is_modern):
    \"\"\"Apply Amazon Prime-style dropdown menu styling\"\"\"
    if is_modern:
        menu.setStyleSheet(\"\"\"
            QMenu {
                background-color: #2d2d2d;
                border: 1px solid #00bcd4;
                border-radius: 8px;
                padding: 8px 0;
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
            }
            QMenu::item {
                padding: 10px 24px;
                color: #e0e0e0;
                font-size: 13px;
                font-weight: 500;
            }
            QMenu::item:selected {
                background-color: rgba(0, 188, 212, 0.2);
                color: #00bcd4;
            }
            QMenu::separator {
                height: 1px;
                background-color: #404040;
                margin: 4px 12px;
            }
        \"\"\")
```

## Testing Steps

### 1. Login Screen
- [ ] Theme selection radio buttons visible (Classic/Modern)
- [ ] Selection persists across sessions
- [ ] Both themes load successfully

### 2. Header Verification
- [ ] Logo displays correctly (🔥 or logo.png)
- [ ] "EMBER EYE COMMAND CENTER" branding visible
- [ ] Group combo box centered
- [ ] Settings gear icon (⚙️) on right
- [ ] Profile icon (👤) next to settings
- [ ] Gradient background renders
- [ ] Cyan border visible (modern theme)

### 3. Dropdown Menus
- [ ] Settings menu shows 13+ items with icons
- [ ] Profile menu shows 2 items
- [ ] Hover effects work smoothly
- [ ] Menu items properly separated
- [ ] PFDS submenu accessible
- [ ] All actions trigger correctly

### 4. Video Wall Tab
- [ ] Tab labeled "🎥 VIDEO WALL"
- [ ] Grid selector shows 2×2, 3×3, 4×4, 5×5
- [ ] Control bar styled with semi-transparent background
- [ ] Navigation buttons circular with hover effects
- [ ] Video tiles spaced 2px apart
- [ ] Black background visible between tiles
- [ ] Videos fill tiles completely

### 5. Other Tabs
- [ ] "📊 ANALYTICS" tab (if Grafana enabled)
- [ ] "🚨 ANOMALIES" tab
- [ ] "⚠️ DEVICES" tab
- [ ] Tab hover effects work
- [ ] Selected tab has cyan border on top

### 6. Status Bar
- [ ] Gradient background matches header
- [ ] Cyan text color
- [ ] Status messages appear
- [ ] TCP indicator visible

## Color Palette Reference

### Modern Theme
- **Background Dark**: #1a1a1a
- **Background Medium**: #252525
- **Background Light**: #2d2d2d
- **Text Primary**: #e0e0e0
- **Text Secondary**: #9e9e9e
- **Accent Cyan**: #00bcd4
- **Accent Cyan Dark**: #00acc1
- **Border/Separator**: #404040

### Classic Theme
- **Background**: #ffffff / #f5f5f5
- **Text**: #2c3e50
- **Accent Blue**: #3498db
- **Border**: #bdc3c7

## Files Modified
1. `main_window.py`:
   - `initUI()` - Full window structure with command center header
   - `init_command_center_header()` - Hollywood-style header with logo and menus
   - `init_header_actions()` - Dual icon dropdowns (settings + profile)
   - `_style_dropdown_menu()` - Amazon Prime menu styling
   - `init_rtsp_tab()` - Video wall grid with modern controls
   - Tab names updated with emojis
   - Status bar styling

2. `theme_manager.py` - Already complete
3. `ee_loginwindow.py` - Already complete
4. `video_widget.py` - Already complete (modern controls)

## Known Issues / TODOs
- [ ] Update Grafana tab name to "📊 ANALYTICS" (blocked by QWebEngine availability)
- [ ] Test 5×5 grid with 25+ streams
- [ ] Verify dropdown positioning on different screen sizes
- [ ] Add keyboard shortcuts for menu actions
- [ ] Implement settings persistence for grid size

## Performance Considerations
- Dropdown menus use instant popup (no delay)
- Shadow effects may impact rendering on low-end hardware
- Grid layout optimized with minimal spacing (2px)
- Theme detection cached at init to avoid repeated property lookups

## User Experience Flow
```
1. Login → Select theme (Classic/Modern)
   ↓
2. Header loads with branding, group selector, icons
   ↓
3. Click ⚙️ → Settings dropdown appears
   ↓
4. Click 👤 → Profile dropdown appears
   ↓
5. Video Wall tab loads with grid selector
   ↓
6. Select grid size → Videos rearrange
   ↓
7. Navigate pages with ◀ ▶ buttons
```

## Success Criteria
✅ **Completed**:
- Dual theme system
- Theme persistence
- Modern styling (600+ lines QSS)
- Video widget enhancements

🎯 **In Progress**:
- Hollywood command center header
- Dual dropdown menu system
- Amazon Prime-style menus
- Video wall grid layout
- Comprehensive tab naming

## Next Steps
1. Apply all changes to `main_window.py` using careful string replacements
2. Test compilation and syntax
3. Launch application with Modern theme selected
4. Verify all visual elements render correctly
5. Test dropdown interactions
6. Validate video wall grid at all sizes
7. Create screenshots for documentation

---
**Created**: December 2025  
**Status**: Phase 1 Complete, Phase 2 In Progress  
**Target**: Professional Command Center Aesthetic
