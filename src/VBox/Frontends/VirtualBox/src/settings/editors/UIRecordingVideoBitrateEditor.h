/* $Id: UIRecordingVideoBitrateEditor.h 111914 2025-11-27 11:37:23Z serkan.bayraktar@oracle.com $ */
/** @file
 * VBox Qt GUI - UIRecordingVideoBitrateEditor class declaration.
 */

/*
 * Copyright (C) 2006-2025 Oracle and/or its affiliates.
 *
 * This file is part of VirtualBox base platform packages, as
 * available from https://www.virtualbox.org.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License
 * as published by the Free Software Foundation, in version 3 of the
 * License.
 *
 * This program is distributed in the hope that it will be useful, but
 * WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program; if not, see <https://www.gnu.org/licenses>.
 *
 * SPDX-License-Identifier: GPL-3.0-only
 */

#ifndef FEQT_INCLUDED_SRC_settings_editors_UIRecordingVideoBitrateEditor_h
#define FEQT_INCLUDED_SRC_settings_editors_UIRecordingVideoBitrateEditor_h
#ifndef RT_WITHOUT_PRAGMA_ONCE
# pragma once
#endif

/* GUI includes: */
#include "UIEditor.h"
#include "UISettingsDefs.h"

/* COM includes: */
#include "KRecordingCodecDeadline.h"

/* Forward declarations: */
class QCheckBox;
class QComboBox;
class QGridLayout;
class QLabel;
class QSpinBox;
class QWidget;
class QIAdvancedSlider;
class UIFilmContainer;
class UIRecordingFilePathEditor;
class UIRecordingVideoFrameRateEditor;


/** UIEditor sub-class used as a recording settings editor. */
class SHARED_LIBRARY_STUFF UIRecordingVideoBitrateEditor : public UIEditor
{
    Q_OBJECT;
signals:

    void sigBitrateQualitySliderChanged();
    void sigBitrateChanged(int iBitrate);

public:

    /** Constructs editor passing @a pParent to the base-class. */
    UIRecordingVideoBitrateEditor(QWidget *pParent = 0, bool fShowInBasicMode = false);

    /** Defines bitrate @a iRate. */
    void setBitrate(int iRate);
    /** Returns bit rate. */
    int bitrate() const;

    /** Defines quality @a iQuality. */
    void setQuality(int iQuality);
    /** Return the value of the quality slider. */
    int quality() const;

private slots:

    /** Handles translation event. */
    virtual void sltRetranslateUI() RT_OVERRIDE RT_FINAL;
    /** Handles bit rate slider change. */
    void sltHandleBitRateSliderChange();
    /** Handles bit rate spinbox change. */
    void sltHandleBitRateSpinboxChange();

private:

    /** Prepares all. */
    void prepare();
    /** Prepares widgets. */
    void prepareWidgets();
    /** Prepares connections. */
    void prepareConnections();

    /** Populates mode combo-box. */
    void populateComboMode();

    /** @name Widgets
     * @{ */
        /** Holds the bit rate label instance. */
        QLabel             *m_pLabelBitRate;
        /** Holds the bit rate settings widget instance. */
        QWidget            *m_pWidgetBitRateSettings;
        /** Holds the bit rate slider instance. */
        QIAdvancedSlider   *m_pSliderQuality;
        /** Holds the bit rate spinbox instance. */
        QSpinBox           *m_pSpinboxBitRate;
        /** Holds the bit rate min label instance. */
        QLabel             *m_pLabelBitRateMin;
        /** Holds the bit rate med label instance. */
        QLabel             *m_pLabelBitRateMed;
        /** Holds the bit rate max label instance. */
        QLabel             *m_pLabelBitRateMax;
    /** @} */
};

#endif /* !FEQT_INCLUDED_SRC_settings_editors_UIRecordingVideoBitrateEditor_h */
