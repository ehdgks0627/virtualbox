/* $Id: UIRecordingSettingsEditor.h 111932 2025-11-28 11:19:26Z serkan.bayraktar@oracle.com $ */
/** @file
 * VBox Qt GUI - UIRecordingSettingsEditor class declaration.
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

#ifndef FEQT_INCLUDED_SRC_settings_editors_UIRecordingSettingsEditor_h
#define FEQT_INCLUDED_SRC_settings_editors_UIRecordingSettingsEditor_h
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
class UIRecordingVideoBitrateEditor;
class UIRecordingVideoFrameRateEditor;
class UIRecordingVideoFrameSizeEditor;

/** UIEditor sub-class used as a recording settings editor. */
class SHARED_LIBRARY_STUFF UIRecordingSettingsEditor : public UIEditor
{
    Q_OBJECT;

public:

    /** Constructs editor passing @a pParent to the base-class. */
    UIRecordingSettingsEditor(QWidget *pParent = 0);

    /** Defines whether feature is @a fEnabled. */
    void setFeatureEnabled(bool fEnabled);
    /** Returns whether feature is enabled. */
    bool isFeatureEnabled() const;

    /** Defines whether options are @a fAvailable. */
    void setOptionsAvailable(bool fAvailable);

    /** Defines @a enmMode. */
    void setMode(UISettingsDefs::RecordingMode enmMode);
    /** Return mode. */
    UISettingsDefs::RecordingMode mode() const;

    /** Defines @a strFolder. */
    void setFolder(const QString &strFolder);
    /** Returns folder. */
    QString folder() const;
    /** Defines @a strFilePath. */
    void setFilePath(const QString &strFilePath);
    /** Returns file path. */
    QString filePath() const;

    /** Defines frame @a iWidth. */
    void setFrameWidth(int iWidth);
    /** Returns frame width. */
    int frameWidth() const;
    /** Defines frame @a iHeight. */
    void setFrameHeight(int iHeight);
    /** Returns frame height. */
    int frameHeight() const;

    /** Defines frame @a iRate. */
    void setFrameRate(int iRate);
    /** Returns frame rate. */
    int frameRate() const;

    /** Defines bitrate @a iRate. */
    void setBitrate(int iRate);
    /** Returns bitrate. */
    int bitrate() const;

    /** Defines video @a enmQuality. */
    void setVideoQuality(KRecordingCodecDeadline enmQuality);
    /** Returns video quality. */
    KRecordingCodecDeadline videoQuality() const;

    /** Defines audio @a strProfile. */
    void setAudioProfile(const QString &strProfile);
    /** Returns audio profile. */
    QString audioProfile() const;

    /** Defines enabled @a screens. */
    void setScreens(const QVector<bool> &screens);
    /** Returns enabled screens. */
    QVector<bool> screens() const;

protected:

    /** Handles filter change. */
    virtual void handleFilterChange() RT_OVERRIDE;

private slots:

    /** Handles translation event. */
    virtual void sltRetranslateUI() RT_OVERRIDE RT_FINAL;
    /** Handles feature toggling. */
    void sltHandleFeatureToggled();
    /** Handles mode change. */
    void sltHandleModeComboChange();
    /** Handles frame rate change. */
    void sltHandleFrameRateChange(int iFrameRate);
    /** Handles bit rate quality slider change. */
    void sltHandleBitrateQualitySliderChange();
    /** Handles bit rate  change. */
    void sltHandleBitrateChange(int iBitrate);

private:

    /** Prepares all. */
    void prepare();
    /** Prepares widgets. */
    void prepareWidgets();
    /** Prepares connections. */
    void prepareConnections();

    /** Populates mode combo-box. */
    void populateComboMode();

    /** Updates widget visibility. */
    void updateWidgetVisibility();
    /** Updates widget availability. */
    void updateWidgetAvailability();
    /** Updates recording file size hint. */
    void updateRecordingFileSizeHint();

    /** Updates minimum layout hint. */
    void updateMinimumLayoutHint();

    /** Calculates recording bit rate for passed @a iFrameWidth, @a iFrameHeight, @a iFrameRate and @a iQuality. */
    static int calculateBitrate(int iFrameWidth, int iFrameHeight, int iFrameRate, int iQuality);
    /** Calculates recording quality for passed @a iFrameWidth, @a iFrameHeight, @a iFrameRate and @a iBitrate. */
    static int calculateQuality(int iFrameWidth, int iFrameHeight, int iFrameRate, int iBitRate);

    /** @name Values
     * @{ */
        /** Holds whether feature is enabled. */
        bool  m_fFeatureEnabled;

        /** Holds whether options are available. */
        bool  m_fOptionsAvailable;

        /** Holds the list of supported modes. */
        QVector<UISettingsDefs::RecordingMode>  m_supportedValues;
        /** Holds the mode. */
        UISettingsDefs::RecordingMode           m_enmMode;

        /** Holds the frame width. */
        int                      m_iFrameWidth;
        /** Holds the frame height. */
        int                      m_iFrameHeight;
        /** Holds the bitrate. */
        int                      m_iBitrate;
        /** Holds the video quality. */
        KRecordingCodecDeadline  m_enmVideoQuality;
        /** Holds the audio profile. */
        QString                  m_strAudioProfile;

        /** Holds the screens. */
        QVector<bool>  m_screens;
    /** @} */

    /** @name Widgets
     * @{ */
        /** Holds the feature check-box instance. */
        QCheckBox          *m_pCheckboxFeature;
        /** Holds the settings layout instance. */
        QGridLayout        *m_pLayoutSettings;
        /** Holds the mode label instance. */
        QLabel             *m_pLabelMode;
        /** Holds the mode combo instance. */
        QComboBox          *m_pComboMode;
        /** Holds the file path editor instance. */
        UIRecordingFilePathEditor *m_pEditorFilePath;
        /** Holds the frame size editor. */
        UIRecordingVideoFrameSizeEditor *m_pEditorFrameSize;
        /** Holds the frame rate editor instance. */
        UIRecordingVideoFrameRateEditor *m_pEditorFrameRate;
        /** Holds the bit rate editor instance. */
        UIRecordingVideoBitrateEditor *m_pEditorBitrate;
        /** Holds the video quality label instance. */
        QLabel             *m_pLabelVideoQuality;
        /** Holds the video quality settings widget instance. */
        QWidget            *m_pWidgetVideoQualitySettings;
        /** Holds the video quality slider instance. */
        QIAdvancedSlider   *m_pSliderVideoQuality;
        /** Holds the video quality min label instance. */
        QLabel             *m_pLabelVideoQualityMin;
        /** Holds the video quality med label instance. */
        QLabel             *m_pLabelVideoQualityMed;
        /** Holds the video quality max label instance. */
        QLabel             *m_pLabelVideoQualityMax;
        /** Holds the audio profile label instance. */
        QLabel             *m_pLabelAudioProfile;
        /** Holds the audio profile settings widget instance. */
        QWidget            *m_pWidgetAudioProfileSettings;
        /** Holds the audio profile slider instance. */
        QIAdvancedSlider   *m_pSliderAudioProfile;
        /** Holds the audio profile min label instance. */
        QLabel             *m_pLabelAudioProfileMin;
        /** Holds the audio profile med label instance. */
        QLabel             *m_pLabelAudioProfileMed;
        /** Holds the audio profile max label instance. */
        QLabel             *m_pLabelAudioProfileMax;
        /** Holds the size hint label instance. */
        QLabel             *m_pLabelSizeHint;
        /** Holds the screens label instance. */
        QLabel             *m_pLabelScreens;
        /** Holds the screens scroller instance. */
        UIFilmContainer    *m_pScrollerScreens;
    /** @} */
};

#endif /* !FEQT_INCLUDED_SRC_settings_editors_UIRecordingSettingsEditor_h */
