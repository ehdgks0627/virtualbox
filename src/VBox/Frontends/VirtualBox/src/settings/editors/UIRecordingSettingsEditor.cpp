/* $Id: UIRecordingSettingsEditor.cpp 111932 2025-11-28 11:19:26Z serkan.bayraktar@oracle.com $ */
/** @file
 * VBox Qt GUI - UIRecordingSettingsEditor class implementation.
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

/* Qt includes: */
#include <QCheckBox>
#include <QComboBox>
#include <QHBoxLayout>
#include <QGridLayout>
#include <QLabel>
#include <QSpinBox>
#include <QVBoxLayout>

/* GUI includes: */
#include "QIAdvancedSlider.h"
#include "UICommon.h"
#include "UIConverter.h"
#include "UIFilmContainer.h"
#include "UIGlobalSession.h"
#include "UIRecordingSettingsEditor.h"
#include "UIRecordingFilePathEditor.h"
#include "UIRecordingVideoBitrateEditor.h"
#include "UIRecordingVideoFrameRateEditor.h"
#include "UIRecordingVideoFrameSizeEditor.h"

/* COM includes: */
#include "CSystemProperties.h"

/* Defines: */
#define VIDEO_CAPTURE_BIT_RATE_MIN 32
#define VIDEO_CAPTURE_BIT_RATE_MAX 2048


UIRecordingSettingsEditor::UIRecordingSettingsEditor(QWidget *pParent /* = 0 */)
    : UIEditor(pParent, true /* show in basic mode */)
    , m_fFeatureEnabled(false)
    , m_fOptionsAvailable(false)
    , m_enmMode(UISettingsDefs::RecordingMode_Max)
    , m_iFrameWidth(0)
    , m_iFrameHeight(0)
    , m_iBitrate(0)
    , m_pCheckboxFeature(0)
    , m_pLayoutSettings(0)
    , m_pLabelMode(0)
    , m_pComboMode(0)
    , m_pEditorFilePath(0)
    , m_pEditorFrameSize(0)
    , m_pEditorFrameRate(0)
    , m_pEditorBitrate(0)
    , m_pLabelVideoQuality(0)
    , m_pWidgetVideoQualitySettings(0)
    , m_pSliderVideoQuality(0)
    , m_pLabelVideoQualityMin(0)
    , m_pLabelVideoQualityMed(0)
    , m_pLabelVideoQualityMax(0)
    , m_pLabelAudioProfile(0)
    , m_pWidgetAudioProfileSettings(0)
    , m_pSliderAudioProfile(0)
    , m_pLabelAudioProfileMin(0)
    , m_pLabelAudioProfileMed(0)
    , m_pLabelAudioProfileMax(0)
    , m_pLabelSizeHint(0)
    , m_pLabelScreens(0)
    , m_pScrollerScreens(0)
{
    prepare();
}

void UIRecordingSettingsEditor::setFeatureEnabled(bool fEnabled)
{
    /* Update cached value and
     * check-box if value has changed: */
    if (m_fFeatureEnabled != fEnabled)
    {
        m_fFeatureEnabled = fEnabled;
        if (m_pCheckboxFeature)
        {
            m_pCheckboxFeature->setChecked(m_fFeatureEnabled);
            sltHandleFeatureToggled();
        }
    }
}

bool UIRecordingSettingsEditor::isFeatureEnabled() const
{
    return m_pCheckboxFeature ? m_pCheckboxFeature->isChecked() : m_fFeatureEnabled;
}

void UIRecordingSettingsEditor::setOptionsAvailable(bool fAvailable)
{
    /* Update cached value and
     * widget availability if value has changed: */
    if (m_fOptionsAvailable != fAvailable)
    {
        m_fOptionsAvailable = fAvailable;
        updateWidgetAvailability();
    }
}

void UIRecordingSettingsEditor::setMode(UISettingsDefs::RecordingMode enmMode)
{
    /* Update cached value and
     * combo if value has changed: */
    if (m_enmMode != enmMode)
    {
        m_enmMode = enmMode;
        populateComboMode();
        updateWidgetVisibility();
    }
}

UISettingsDefs::RecordingMode UIRecordingSettingsEditor::mode() const
{
    return m_pComboMode ? m_pComboMode->currentData().value<UISettingsDefs::RecordingMode>() : m_enmMode;
}

void UIRecordingSettingsEditor::setFolder(const QString &strFolder)
{
    if (m_pEditorFilePath)
        m_pEditorFilePath->setFolder(strFolder);
}

QString UIRecordingSettingsEditor::folder() const
{
    return m_pEditorFilePath ? m_pEditorFilePath->folder() : QString();
}

void UIRecordingSettingsEditor::setFilePath(const QString &strFilePath)
{
    if (m_pEditorFilePath)
        m_pEditorFilePath->setFilePath(strFilePath);
}

QString UIRecordingSettingsEditor::filePath() const
{
    return m_pEditorFilePath ? m_pEditorFilePath->filePath() : QString();
}

void UIRecordingSettingsEditor::setFrameWidth(int iWidth)
{
    if (m_pEditorFrameSize)
        m_pEditorFrameSize->setFrameWidth(iWidth);
}

int UIRecordingSettingsEditor::frameWidth() const
{
    return m_pEditorFrameSize ? m_pEditorFrameSize->frameWidth() : 0;
}

void UIRecordingSettingsEditor::setFrameHeight(int iHeight)
{
    if (m_pEditorFrameSize)
        m_pEditorFrameSize->setFrameHeight(iHeight);
}

int UIRecordingSettingsEditor::frameHeight() const
{
    return m_pEditorFrameSize ? m_pEditorFrameSize->frameHeight() : 0;
}

void UIRecordingSettingsEditor::setFrameRate(int iRate)
{
    if (m_pEditorFrameRate)
        m_pEditorFrameRate->setFrameRate(iRate);
}

int UIRecordingSettingsEditor::frameRate() const
{
    return m_pEditorFrameRate ? m_pEditorFrameRate->frameRate() : 0;
}

void UIRecordingSettingsEditor::setBitrate(int iRate)
{
    /* Update cached value and
     * spin-box if value has changed: */
    if (m_iBitrate != iRate)
    {
        m_iBitrate = iRate;
        if (m_pEditorBitrate)
            m_pEditorBitrate->setBitrate(m_iBitrate);
    }
}

int UIRecordingSettingsEditor::bitrate() const
{
    return m_pEditorBitrate ? m_pEditorBitrate->bitrate() : m_iBitrate;
}

void UIRecordingSettingsEditor::setVideoQuality(KRecordingCodecDeadline enmQuality)
{
    /* Update cached value and
     * slider if value has changed: */
    if (m_enmVideoQuality != enmQuality)
    {
        m_enmVideoQuality = enmQuality;
        if (m_pSliderVideoQuality)
            m_pSliderVideoQuality->setValue((int)enmQuality);
    }
}

KRecordingCodecDeadline UIRecordingSettingsEditor::videoQuality() const
{
    return m_pSliderVideoQuality ? (KRecordingCodecDeadline)m_pSliderVideoQuality->value() : m_enmVideoQuality;
}

void UIRecordingSettingsEditor::setAudioProfile(const QString &strProfile)
{
    /* Update cached value and
     * slider if value has changed: */
    if (m_strAudioProfile != strProfile)
    {
        m_strAudioProfile = strProfile;
        if (m_pSliderAudioProfile)
        {
            const QStringList profiles = QStringList() << "low" << "med" << "high";
            int iIndexOfProfile = profiles.indexOf(m_strAudioProfile);
            if (iIndexOfProfile == -1)
                iIndexOfProfile = 1; // "med" by default
            m_pSliderAudioProfile->setValue(iIndexOfProfile);
        }
    }
}

QString UIRecordingSettingsEditor::audioProfile() const
{
    if (m_pSliderAudioProfile)
    {
        const QStringList profiles = QStringList() << "low" << "med" << "high";
        return profiles.value(m_pSliderAudioProfile->value(), "med" /* by default */);
    }
    return m_strAudioProfile;
}

void UIRecordingSettingsEditor::setScreens(const QVector<bool> &screens)
{
    /* Update cached value and
     * editor if value has changed: */
    if (m_screens != screens)
    {
        m_screens = screens;
        if (m_pScrollerScreens)
            m_pScrollerScreens->setValue(m_screens);
    }
}

QVector<bool> UIRecordingSettingsEditor::screens() const
{
    return m_pScrollerScreens ? m_pScrollerScreens->value() : m_screens;
}

void UIRecordingSettingsEditor::handleFilterChange()
{
    updateMinimumLayoutHint();
}

void UIRecordingSettingsEditor::sltRetranslateUI()
{
    m_pCheckboxFeature->setText(tr("&Enable Recording"));
    m_pCheckboxFeature->setToolTip(tr("VirtualBox will record the virtual machine session as a video file"));

    m_pLabelMode->setText(tr("Recording &Mode"));
    for (int iIndex = 0; iIndex < m_pComboMode->count(); ++iIndex)
    {
        const UISettingsDefs::RecordingMode enmType =
            m_pComboMode->itemData(iIndex).value<UISettingsDefs::RecordingMode>();
        m_pComboMode->setItemText(iIndex, gpConverter->toString(enmType));
    }
    m_pComboMode->setToolTip(tr("Recording mode"));

    m_pLabelVideoQuality->setText(tr("&Video Quality"));
    m_pSliderVideoQuality->setToolTip(tr("Video quality. Increasing this value will make the video "
                                         "look better at the cost of a decreased VM performance."));
    m_pLabelVideoQualityMin->setText(tr("default", "quality"));
    m_pLabelVideoQualityMed->setText(tr("good", "quality"));
    m_pLabelVideoQualityMax->setText(tr("best", "quality"));

    m_pLabelAudioProfile->setText(tr("&Audio Profile"));
    m_pSliderAudioProfile->setToolTip(tr("Audio profile. Increasing this value will make the audio "
                                         "sound better at the cost of an increased file size."));
    m_pLabelAudioProfileMin->setText(tr("low", "profile"));
    m_pLabelAudioProfileMed->setText(tr("medium", "profile"));
    m_pLabelAudioProfileMax->setText(tr("high", "profile"));

    m_pLabelScreens->setText(tr("Scree&ns"));

    updateRecordingFileSizeHint();
    updateMinimumLayoutHint();
}

void UIRecordingSettingsEditor::sltHandleFeatureToggled()
{
    /* Update widget availability: */
    updateWidgetAvailability();
}

void UIRecordingSettingsEditor::sltHandleModeComboChange()
{
    /* Update widget availability: */
    updateWidgetAvailability();
}

void UIRecordingSettingsEditor::sltHandleFrameRateChange(int iFrameRate)
{
    Q_UNUSED(iFrameRate);
    /* Update quality and bit rate: */
    sltHandleBitrateQualitySliderChange();
}

void UIRecordingSettingsEditor::sltHandleBitrateQualitySliderChange()
{
    /* Calculate/apply proposed bit rate: */
    m_pEditorBitrate->blockSignals(true);
    m_pEditorBitrate->setBitrate(calculateBitrate(m_pEditorFrameSize->frameWidth(),
                                                  m_pEditorFrameSize->frameHeight(),
                                                  m_pEditorFrameRate->frameRate(),
                                                  m_pEditorBitrate->quality()));
    m_pEditorBitrate->blockSignals(false);
    updateRecordingFileSizeHint();
}

void UIRecordingSettingsEditor::sltHandleBitrateChange(int iBitrate)
{
    /* Calculate/apply proposed quality: */
    m_pEditorBitrate->blockSignals(true);
    m_pEditorBitrate->setQuality(calculateQuality(m_pEditorFrameSize->frameWidth(),
                                                  m_pEditorFrameSize->frameHeight(),
                                                  m_pEditorFrameRate->frameRate(),
                                                  iBitrate));
    m_pEditorBitrate->blockSignals(false);
    updateRecordingFileSizeHint();
}

void UIRecordingSettingsEditor::prepare()
{
    /* Prepare everything: */
    prepareWidgets();
    prepareConnections();

    /* Apply language settings: */
    sltRetranslateUI();
}

void UIRecordingSettingsEditor::prepareWidgets()
{
    /* Prepare main layout: */
    QGridLayout *pLayout = new QGridLayout(this);
    if (pLayout)
    {
        pLayout->setContentsMargins(0, 0, 0, 0);
        pLayout->setColumnStretch(1, 1);

        /* Prepare 'feature' check-box: */
        m_pCheckboxFeature = new QCheckBox(this);
        if (m_pCheckboxFeature)
        {
            // this name is used from outside, have a look at UIMachineLogic..
            m_pCheckboxFeature->setObjectName("m_pCheckboxVideoCapture");
            pLayout->addWidget(m_pCheckboxFeature, 0, 0, 1, 2);
        }

        /* Prepare 20-px shifting spacer: */
        QSpacerItem *pSpacerItem = new QSpacerItem(20, 0, QSizePolicy::Fixed, QSizePolicy::Minimum);
        if (pSpacerItem)
            pLayout->addItem(pSpacerItem, 1, 0);

        /* Prepare 'settings' widget: */
        QWidget *pWidgetSettings = new QWidget(this);
        if (pWidgetSettings)
        {
            /* Prepare recording settings widget layout: */
            m_pLayoutSettings = new QGridLayout(pWidgetSettings);
            if (m_pLayoutSettings)
            {
                int iLayoutSettingsRow = 0;
                m_pLayoutSettings->setContentsMargins(0, 0, 0, 0);

                /* Prepare recording mode label: */
                m_pLabelMode = new QLabel(pWidgetSettings);
                if (m_pLabelMode)
                {
                    m_pLabelMode->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
                    m_pLayoutSettings->addWidget(m_pLabelMode, iLayoutSettingsRow, 0);
                }
                /* Prepare recording mode combo: */
                m_pComboMode = new QComboBox(pWidgetSettings);
                if (m_pComboMode)
                {
                    if (m_pLabelMode)
                        m_pLabelMode->setBuddy(m_pComboMode);
                    m_pComboMode->addItem(QString(), QVariant::fromValue(UISettingsDefs::RecordingMode_VideoAudio));
                    m_pComboMode->addItem(QString(), QVariant::fromValue(UISettingsDefs::RecordingMode_VideoOnly));
                    m_pComboMode->addItem(QString(), QVariant::fromValue(UISettingsDefs::RecordingMode_AudioOnly));

                    m_pLayoutSettings->addWidget(m_pComboMode, iLayoutSettingsRow, 1, 1, 3);
                }
                /* Prepare recording file path editor: */
                m_pEditorFilePath = new UIRecordingFilePathEditor(pWidgetSettings, false);
                if (m_pEditorFilePath)
                {
                    addEditor(m_pEditorFilePath);
                    m_pLayoutSettings->addWidget(m_pEditorFilePath, ++iLayoutSettingsRow, 0, 1, 4);
                }
                /* Prepare recording frame size editor: */
                m_pEditorFrameSize = new UIRecordingVideoFrameSizeEditor(pWidgetSettings, true);
                if (m_pEditorFrameSize)
                {
                    addEditor(m_pEditorFrameSize);
                    m_pLayoutSettings->addWidget(m_pEditorFrameSize, ++iLayoutSettingsRow, 0, 1, 4);
                }
                /* Prepare recording frame rate editor: */
                m_pEditorFrameRate = new UIRecordingVideoFrameRateEditor(pWidgetSettings, false);
                if (m_pEditorFrameRate)
                {
                    addEditor(m_pEditorFrameRate);
                    m_pLayoutSettings->addWidget(m_pEditorFrameRate, ++iLayoutSettingsRow, 0, 1, 4);
                }
                m_pEditorBitrate = new UIRecordingVideoBitrateEditor(pWidgetSettings, true);
                if (m_pEditorBitrate)
                {
                    addEditor(m_pEditorBitrate);
                    m_pLayoutSettings->addWidget(m_pEditorBitrate, ++iLayoutSettingsRow, 0, 1, 4);
                }

                /* Prepare recording video quality label: */
                m_pLabelVideoQuality = new QLabel(pWidgetSettings);
                if (m_pLabelVideoQuality)
                {
                    m_pLabelVideoQuality->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
                    m_pLayoutSettings->addWidget(m_pLabelVideoQuality, 7, 0);
                }
                /* Prepare recording video quality widget: */
                m_pWidgetVideoQualitySettings = new QWidget(pWidgetSettings);
                if (m_pWidgetVideoQualitySettings)
                {
                    /* Prepare recording video quality layout: */
                    QVBoxLayout *pLayoutRecordingVideoQuality = new QVBoxLayout(m_pWidgetVideoQualitySettings);
                    if (pLayoutRecordingVideoQuality)
                    {
                        pLayoutRecordingVideoQuality->setContentsMargins(0, 0, 0, 0);

                        /* Prepare recording video quality slider: */
                        m_pSliderVideoQuality = new QIAdvancedSlider(m_pWidgetVideoQualitySettings);
                        if (m_pSliderVideoQuality)
                        {
                            if (m_pLabelVideoQuality)
                                m_pLabelVideoQuality->setBuddy(m_pSliderVideoQuality);
                            m_pSliderVideoQuality->setOrientation(Qt::Horizontal);
                            m_pSliderVideoQuality->setMinimum(KRecordingCodecDeadline_Default);
                            m_pSliderVideoQuality->setMaximum(KRecordingCodecDeadline_Max - 1);
                            m_pSliderVideoQuality->setPageStep(1);
                            m_pSliderVideoQuality->setSingleStep(1);
                            m_pSliderVideoQuality->setTickInterval(1);
                            m_pSliderVideoQuality->setSnappingEnabled(true);
                            m_pSliderVideoQuality->setOptimalHint(KRecordingCodecDeadline_Default,
                                                                  KRecordingCodecDeadline_Realtime);
                            m_pSliderVideoQuality->setWarningHint(KRecordingCodecDeadline_Realtime,
                                                                  KRecordingCodecDeadline_Max - 1);

                            pLayoutRecordingVideoQuality->addWidget(m_pSliderVideoQuality);
                        }
                        /* Prepare recording video quality scale layout: */
                        QHBoxLayout *pLayoutRecordingVideoQualityScale = new QHBoxLayout;
                        if (pLayoutRecordingVideoQualityScale)
                        {
                            pLayoutRecordingVideoQualityScale->setContentsMargins(0, 0, 0, 0);

                            /* Prepare recording video quality min label: */
                            m_pLabelVideoQualityMin = new QLabel(m_pWidgetVideoQualitySettings);
                            if (m_pLabelVideoQualityMin)
                                pLayoutRecordingVideoQualityScale->addWidget(m_pLabelVideoQualityMin);
                            pLayoutRecordingVideoQualityScale->addStretch();
                            /* Prepare recording video quality med label: */
                            m_pLabelVideoQualityMed = new QLabel(m_pWidgetVideoQualitySettings);
                            if (m_pLabelVideoQualityMed)
                                pLayoutRecordingVideoQualityScale->addWidget(m_pLabelVideoQualityMed);
                            pLayoutRecordingVideoQualityScale->addStretch();
                            /* Prepare recording video quality max label: */
                            m_pLabelVideoQualityMax = new QLabel(m_pWidgetVideoQualitySettings);
                            if (m_pLabelVideoQualityMax)
                                pLayoutRecordingVideoQualityScale->addWidget(m_pLabelVideoQualityMax);

                            pLayoutRecordingVideoQuality->addLayout(pLayoutRecordingVideoQualityScale);
                        }
                    }

                    m_pLayoutSettings->addWidget(m_pWidgetVideoQualitySettings, 7, 1, 2, 1);
                }

                /* Prepare recording audio profile label: */
                m_pLabelAudioProfile = new QLabel(pWidgetSettings);
                if (m_pLabelAudioProfile)
                {
                    m_pLabelAudioProfile->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
                    m_pLayoutSettings->addWidget(m_pLabelAudioProfile, 9, 0);
                }
                /* Prepare recording audio profile widget: */
                m_pWidgetAudioProfileSettings = new QWidget(pWidgetSettings);
                if (m_pWidgetAudioProfileSettings)
                {
                    /* Prepare recording audio profile layout: */
                    QVBoxLayout *pLayoutRecordingAudioProfile = new QVBoxLayout(m_pWidgetAudioProfileSettings);
                    if (pLayoutRecordingAudioProfile)
                    {
                        pLayoutRecordingAudioProfile->setContentsMargins(0, 0, 0, 0);

                        /* Prepare recording audio profile slider: */
                        m_pSliderAudioProfile = new QIAdvancedSlider(m_pWidgetAudioProfileSettings);
                        if (m_pSliderAudioProfile)
                        {
                            if (m_pLabelAudioProfile)
                                m_pLabelAudioProfile->setBuddy(m_pSliderAudioProfile);
                            m_pSliderAudioProfile->setOrientation(Qt::Horizontal);
                            m_pSliderAudioProfile->setMinimum(0);
                            m_pSliderAudioProfile->setMaximum(2);
                            m_pSliderAudioProfile->setPageStep(1);
                            m_pSliderAudioProfile->setSingleStep(1);
                            m_pSliderAudioProfile->setTickInterval(1);
                            m_pSliderAudioProfile->setSnappingEnabled(true);
                            m_pSliderAudioProfile->setOptimalHint(0, 1);
                            m_pSliderAudioProfile->setWarningHint(1, 2);

                            pLayoutRecordingAudioProfile->addWidget(m_pSliderAudioProfile);
                        }
                        /* Prepare recording audio profile scale layout: */
                        QHBoxLayout *pLayoutRecordingAudioProfileScale = new QHBoxLayout;
                        if (pLayoutRecordingAudioProfileScale)
                        {
                            pLayoutRecordingAudioProfileScale->setContentsMargins(0, 0, 0, 0);

                            /* Prepare recording audio profile min label: */
                            m_pLabelAudioProfileMin = new QLabel(m_pWidgetAudioProfileSettings);
                            if (m_pLabelAudioProfileMin)
                                pLayoutRecordingAudioProfileScale->addWidget(m_pLabelAudioProfileMin);
                            pLayoutRecordingAudioProfileScale->addStretch();
                            /* Prepare recording audio profile med label: */
                            m_pLabelAudioProfileMed = new QLabel(m_pWidgetAudioProfileSettings);
                            if (m_pLabelAudioProfileMed)
                                pLayoutRecordingAudioProfileScale->addWidget(m_pLabelAudioProfileMed);
                            pLayoutRecordingAudioProfileScale->addStretch();
                            /* Prepare recording audio profile max label: */
                            m_pLabelAudioProfileMax = new QLabel(m_pWidgetAudioProfileSettings);
                            if (m_pLabelAudioProfileMax)
                                pLayoutRecordingAudioProfileScale->addWidget(m_pLabelAudioProfileMax);

                            pLayoutRecordingAudioProfile->addLayout(pLayoutRecordingAudioProfileScale);
                        }
                    }

                    m_pLayoutSettings->addWidget(m_pWidgetAudioProfileSettings, 9, 1, 2, 1);
                }

                /* Prepare recording size hint label: */
                m_pLabelSizeHint = new QLabel(pWidgetSettings);
                if (m_pLabelSizeHint)
                    m_pLayoutSettings->addWidget(m_pLabelSizeHint, 11, 1);

                /* Prepare recording screens label: */
                m_pLabelScreens = new QLabel(pWidgetSettings);
                if (m_pLabelScreens)
                {
                    m_pLabelScreens->setAlignment(Qt::AlignRight | Qt::AlignTop);
                    m_pLayoutSettings->addWidget(m_pLabelScreens, 12, 0);
                }
                /* Prepare recording screens scroller: */
                m_pScrollerScreens = new UIFilmContainer(pWidgetSettings);
                if (m_pScrollerScreens)
                {
                    if (m_pLabelScreens)
                        m_pLabelScreens->setBuddy(m_pScrollerScreens);
                    m_pLayoutSettings->addWidget(m_pScrollerScreens, 12, 1, 1, 3);
                }
            }

            pLayout->addWidget(pWidgetSettings, 1, 1, 1, 2);
        }
    }

    /* Update widget availability: */
    updateWidgetAvailability();
}

void UIRecordingSettingsEditor::prepareConnections()
{
    connect(m_pCheckboxFeature, &QCheckBox::toggled,
            this, &UIRecordingSettingsEditor::sltHandleFeatureToggled);
    connect(m_pComboMode, &QComboBox::currentIndexChanged,
            this, &UIRecordingSettingsEditor::sltHandleModeComboChange);
    connect(m_pEditorFrameSize, &UIRecordingVideoFrameSizeEditor::sigFrameSizeChanged,
            this, &UIRecordingSettingsEditor::sltHandleBitrateQualitySliderChange);
    connect(m_pEditorFrameRate, &UIRecordingVideoFrameRateEditor::sigFrameRateChanged,
            this, &UIRecordingSettingsEditor::sltHandleFrameRateChange);
    connect(m_pEditorBitrate, &UIRecordingVideoBitrateEditor::sigBitrateQualitySliderChanged,
            this, &UIRecordingSettingsEditor::sltHandleBitrateQualitySliderChange);
    connect(m_pEditorBitrate, &UIRecordingVideoBitrateEditor::sigBitrateChanged,
            this, &UIRecordingSettingsEditor::sltHandleBitrateChange);
}

void UIRecordingSettingsEditor::populateComboMode()
{
    if (m_pComboMode)
    {
        /* Clear combo first of all: */
        m_pComboMode->clear();

        /* Load currently supported recording features: */
        const int iSupportedFlag = gpGlobalSession->supportedRecordingFeatures();
        m_supportedValues.clear();
        if (!iSupportedFlag)
            m_supportedValues << UISettingsDefs::RecordingMode_None;
        else
        {
            if (   (iSupportedFlag & KRecordingFeature_Video)
                && (iSupportedFlag & KRecordingFeature_Audio))
                m_supportedValues << UISettingsDefs::RecordingMode_VideoAudio;
            if (iSupportedFlag & KRecordingFeature_Video)
                m_supportedValues << UISettingsDefs::RecordingMode_VideoOnly;
            if (iSupportedFlag & KRecordingFeature_Audio)
                m_supportedValues << UISettingsDefs::RecordingMode_AudioOnly;
        }

        /* Make sure requested value if sane is present as well: */
        if (   m_enmMode != UISettingsDefs::RecordingMode_Max
            && !m_supportedValues.contains(m_enmMode))
            m_supportedValues.prepend(m_enmMode);

        /* Update combo with all the supported values: */
        foreach (const UISettingsDefs::RecordingMode &enmType, m_supportedValues)
            m_pComboMode->addItem(QString(), QVariant::fromValue(enmType));

        /* Look for proper index to choose: */
        const int iIndex = m_pComboMode->findData(QVariant::fromValue(m_enmMode));
        if (iIndex != -1)
            m_pComboMode->setCurrentIndex(iIndex);

        /* Retranslate finally: */
        sltRetranslateUI();
    }
}

void UIRecordingSettingsEditor::updateWidgetVisibility()
{
    /* Only the Audio stuff can be totally disabled, so we will add the code for hiding Audio stuff only: */
    const bool fAudioSettingsVisible =    m_supportedValues.isEmpty()
                                       || m_supportedValues.contains(UISettingsDefs::RecordingMode_AudioOnly);
    m_pWidgetAudioProfileSettings->setVisible(fAudioSettingsVisible);
    m_pLabelAudioProfile->setVisible(fAudioSettingsVisible);
}

void UIRecordingSettingsEditor::updateWidgetAvailability()
{
    const bool fFeatureEnabled = m_pCheckboxFeature->isChecked();
    const UISettingsDefs::RecordingMode enmRecordingMode =
        m_pComboMode->currentData().value<UISettingsDefs::RecordingMode>();
    const bool fRecordVideo =    enmRecordingMode == UISettingsDefs::RecordingMode_VideoOnly
                              || enmRecordingMode == UISettingsDefs::RecordingMode_VideoAudio;
    const bool fRecordAudio =    enmRecordingMode == UISettingsDefs::RecordingMode_AudioOnly
                              || enmRecordingMode == UISettingsDefs::RecordingMode_VideoAudio;

    m_pLabelMode->setEnabled(fFeatureEnabled && m_fOptionsAvailable);
    m_pComboMode->setEnabled(fFeatureEnabled && m_fOptionsAvailable);
    m_pEditorFilePath->setEnabled(fFeatureEnabled && m_fOptionsAvailable);

    m_pEditorFrameSize->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);
    m_pEditorFrameRate->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);
    m_pEditorBitrate->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);

    m_pLabelVideoQuality->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);
    m_pWidgetVideoQualitySettings->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);

    m_pLabelAudioProfile->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordAudio);
    m_pWidgetAudioProfileSettings->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordAudio);

    m_pLabelSizeHint->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);

    m_pLabelScreens->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);
    m_pScrollerScreens->setEnabled(fFeatureEnabled && m_fOptionsAvailable && fRecordVideo);
}

void UIRecordingSettingsEditor::updateRecordingFileSizeHint()
{
    m_pLabelSizeHint->setText(tr("<i>About %1MB per 5 minute video</i>")
                                 .arg(m_pEditorBitrate->bitrate() * 300 / 8 / 1024));
}

void UIRecordingSettingsEditor::updateMinimumLayoutHint()
{
    /* Layout all the editors (local and external), this will work fine after all of them became UIEditors: */
    int iMinimumLayoutHint = 0;
    if (m_pLabelMode && !m_pLabelMode->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pLabelMode->minimumSizeHint().width());
    /* The following editors have own labels, but we want them to be properly layouted according to rest of stuff: */
    if (m_pEditorFilePath && !m_pEditorFilePath->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pEditorFilePath->minimumLabelHorizontalHint());
    if (m_pEditorFrameSize && !m_pEditorFrameSize->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pEditorFrameSize->minimumLabelHorizontalHint());
    if (m_pEditorFrameRate && !m_pEditorFrameRate->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pEditorFrameRate->minimumLabelHorizontalHint());
    if (m_pEditorBitrate && !m_pEditorBitrate->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pEditorBitrate->minimumLabelHorizontalHint());
    if (m_pLabelVideoQuality && !m_pLabelVideoQuality->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pLabelVideoQuality->minimumSizeHint().width());
    if (m_pLabelAudioProfile && !m_pLabelAudioProfile->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pLabelAudioProfile->minimumSizeHint().width());
    if (m_pLabelScreens && !m_pLabelScreens->isHidden())
        iMinimumLayoutHint = qMax(iMinimumLayoutHint, m_pLabelScreens->minimumSizeHint().width());
    if (m_pEditorFilePath)
        m_pEditorFilePath->setMinimumLayoutIndent(iMinimumLayoutHint);
    if (m_pEditorFrameRate)
        m_pEditorFrameRate->setMinimumLayoutIndent(iMinimumLayoutHint);
    if (m_pEditorFrameSize)
        m_pEditorFrameSize->setMinimumLayoutIndent(iMinimumLayoutHint);
    if (m_pEditorBitrate)
        m_pEditorBitrate->setMinimumLayoutIndent(iMinimumLayoutHint);
    if (m_pLayoutSettings)
        m_pLayoutSettings->setColumnMinimumWidth(0, iMinimumLayoutHint);
}

/* static */
int UIRecordingSettingsEditor::calculateBitrate(int iFrameWidth, int iFrameHeight, int iFrameRate, int iQuality)
{
    /* Linear quality<=>bit rate scale-factor: */
    const double dResult = (double)iQuality
                         * (double)iFrameWidth * (double)iFrameHeight * (double)iFrameRate
                         / (double)10 /* translate quality to [%] */
                         / (double)1024 /* translate bit rate to [kbps] */
                         / (double)18.75 /* linear scale factor */;
    return (int)dResult;
}

/* static */
int UIRecordingSettingsEditor::calculateQuality(int iFrameWidth, int iFrameHeight, int iFrameRate, int iBitRate)
{
    /* Linear bit rate<=>quality scale-factor: */
    const double dResult = (double)iBitRate
                         / (double)iFrameWidth / (double)iFrameHeight / (double)iFrameRate
                         * (double)10 /* translate quality to [%] */
                         * (double)1024 /* translate bit rate to [kbps] */
                         * (double)18.75 /* linear scale factor */;
    return (int)dResult;
}
