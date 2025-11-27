/* $Id: UIRecordingVideoBitrateEditor.cpp 111914 2025-11-27 11:37:23Z serkan.bayraktar@oracle.com $ */
/** @file
 * VBox Qt GUI - UIRecordingVideoBitrateEditor class implementation.
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
#include "UIRecordingVideoBitrateEditor.h"
#include "UIRecordingFilePathEditor.h"
#include "UIRecordingVideoFrameRateEditor.h"

/* COM includes: */
#include "CSystemProperties.h"

/* Defines: */
#define VIDEO_CAPTURE_BIT_RATE_MIN 32
#define VIDEO_CAPTURE_BIT_RATE_MAX 2048


UIRecordingVideoBitrateEditor::UIRecordingVideoBitrateEditor(QWidget *pParent /* = 0 */, bool fShowInBasicMode /* = false */)
    : UIEditor(pParent, fShowInBasicMode)
    , m_pLabelBitRate(0)
    , m_pWidgetBitRateSettings(0)
    , m_pSliderQuality(0)
    , m_pSpinboxBitRate(0)
    , m_pLabelBitRateMin(0)
    , m_pLabelBitRateMed(0)
    , m_pLabelBitRateMax(0)
{
    prepare();
}

void UIRecordingVideoBitrateEditor::setBitrate(int iRate)
{
    if (!m_pSpinboxBitRate || m_pSpinboxBitRate->value() == iRate)
        return;
    m_pSpinboxBitRate->setValue(iRate);
}

int UIRecordingVideoBitrateEditor::bitrate() const
{
    return m_pSpinboxBitRate ? m_pSpinboxBitRate->value() : 0;
}

void UIRecordingVideoBitrateEditor::setQuality(int iQuality)
{
    if (!m_pSliderQuality || m_pSliderQuality->value() == iQuality)
        return;
    m_pSliderQuality->setValue(iQuality);
}

int UIRecordingVideoBitrateEditor::quality() const
{
    return m_pSliderQuality ? m_pSliderQuality->value() : 0;
}

void UIRecordingVideoBitrateEditor::sltRetranslateUI()
{
    m_pLabelBitRate->setText(tr("&Bitrate"));
    m_pSliderQuality->setToolTip(tr("Bitrate. Increasing this value will make the video "
                                    "look better at the cost of an increased file size."));
    m_pSpinboxBitRate->setSuffix(QString(" %1").arg(tr("kbps")));
    m_pSpinboxBitRate->setToolTip(tr("Bitrate in kilobits per second. Increasing this value "
                                     "will make the video look better at the cost of an increased file size."));
    m_pLabelBitRateMin->setText(tr("low", "quality"));
    m_pLabelBitRateMed->setText(tr("medium", "quality"));
    m_pLabelBitRateMax->setText(tr("high", "quality"));
}

void UIRecordingVideoBitrateEditor::sltHandleBitRateSliderChange()
{
    emit sigBitrateQualitySliderChanged();
    // /* Calculate/apply proposed bit rate: */
    // m_pSpinboxBitRate->blockSignals(true);
    // m_pSpinboxBitRate->setValue(calculateBitRate(m_pSpinboxFrameWidth->value(),
    //                                              m_pSpinboxFrameHeight->value(),
    //                                              m_pEditorFrameRate->frameRate(),
    //                                              m_pSliderQuality->value()));
    // m_pSpinboxBitRate->blockSignals(false);
    // updateRecordingFileSizeHint();
}

void UIRecordingVideoBitrateEditor::sltHandleBitRateSpinboxChange()
{
    emit sigBitrateChanged(m_pSpinboxBitRate->value());
    // /* Calculate/apply proposed quality: */
    // m_pSliderQuality->blockSignals(true);
    // m_pSliderQuality->setValue(calculateQuality(m_pSpinboxFrameWidth->value(),
    //                                             m_pSpinboxFrameHeight->value(),
    //                                             m_pEditorFrameRate->frameRate(),
    //                                             m_pSpinboxBitRate->value()));
    // m_pSliderQuality->blockSignals(false);
    // updateRecordingFileSizeHint();
}

void UIRecordingVideoBitrateEditor::prepare()
{
    /* Prepare everything: */
    prepareWidgets();
    prepareConnections();

    /* Apply language settings: */
    sltRetranslateUI();
}

void UIRecordingVideoBitrateEditor::prepareWidgets()
{
    /* Prepare main layout: */
    QHBoxLayout *pLayout = new QHBoxLayout(this);
    if (pLayout)
    {
        pLayout->setContentsMargins(0, 0, 0, 0);

        /* Prepare recording bit rate label: */
        m_pLabelBitRate = new QLabel(this);
        if (m_pLabelBitRate)
        {
            m_pLabelBitRate->setAlignment(Qt::AlignRight | Qt::AlignVCenter);
            pLayout->addWidget(m_pLabelBitRate);
        }
        /* Prepare recording bit rate widget: */
        m_pWidgetBitRateSettings = new QWidget(this);
        if (m_pWidgetBitRateSettings)
        {
            /* Prepare recording bit rate layout: */
            QVBoxLayout *pLayoutRecordingBitRate = new QVBoxLayout(m_pWidgetBitRateSettings);
            if (pLayoutRecordingBitRate)
            {
                pLayoutRecordingBitRate->setContentsMargins(0, 0, 0, 0);

                /* Prepare recording bit rate slider: */
                m_pSliderQuality = new QIAdvancedSlider(m_pWidgetBitRateSettings);
                if (m_pSliderQuality)
                {
                    m_pSliderQuality->setOrientation(Qt::Horizontal);
                    m_pSliderQuality->setMinimum(1);
                    m_pSliderQuality->setMaximum(10);
                    m_pSliderQuality->setPageStep(1);
                    m_pSliderQuality->setSingleStep(1);
                    m_pSliderQuality->setTickInterval(1);
                    m_pSliderQuality->setSnappingEnabled(true);
                    m_pSliderQuality->setOptimalHint(1, 5);
                    m_pSliderQuality->setWarningHint(5, 9);
                    m_pSliderQuality->setErrorHint(9, 10);

                    pLayoutRecordingBitRate->addWidget(m_pSliderQuality);
                }
                /* Prepare recording bit rate scale layout: */
                QHBoxLayout *pLayoutRecordingBitRateScale = new QHBoxLayout;
                if (pLayoutRecordingBitRateScale)
                {
                    pLayoutRecordingBitRateScale->setContentsMargins(0, 0, 0, 0);

                    /* Prepare recording bit rate min label: */
                    m_pLabelBitRateMin = new QLabel(m_pWidgetBitRateSettings);
                    if (m_pLabelBitRateMin)
                        pLayoutRecordingBitRateScale->addWidget(m_pLabelBitRateMin);
                    pLayoutRecordingBitRateScale->addStretch();
                    /* Prepare recording bit rate med label: */
                    m_pLabelBitRateMed = new QLabel(m_pWidgetBitRateSettings);
                    if (m_pLabelBitRateMed)
                        pLayoutRecordingBitRateScale->addWidget(m_pLabelBitRateMed);
                    pLayoutRecordingBitRateScale->addStretch();
                    /* Prepare recording bit rate max label: */
                    m_pLabelBitRateMax = new QLabel(m_pWidgetBitRateSettings);
                    if (m_pLabelBitRateMax)
                        pLayoutRecordingBitRateScale->addWidget(m_pLabelBitRateMax);

                    pLayoutRecordingBitRate->addLayout(pLayoutRecordingBitRateScale);
                }
            }

            pLayout->addWidget(m_pWidgetBitRateSettings);
        }
        /* Prepare recording bit rate spinbox: */
        m_pSpinboxBitRate = new QSpinBox(this);
        if (m_pSpinboxBitRate)
        {
            if (m_pLabelBitRate)
                m_pLabelBitRate->setBuddy(m_pSpinboxBitRate);
            uiCommon().setMinimumWidthAccordingSymbolCount(m_pSpinboxBitRate, 5);
            m_pSpinboxBitRate->setMinimum(VIDEO_CAPTURE_BIT_RATE_MIN);
            m_pSpinboxBitRate->setMaximum(VIDEO_CAPTURE_BIT_RATE_MAX);

            pLayout->addWidget(m_pSpinboxBitRate);
        }


    }

}

void UIRecordingVideoBitrateEditor::prepareConnections()
{
    connect(m_pSliderQuality, &QIAdvancedSlider::valueChanged,
            this, &UIRecordingVideoBitrateEditor::sltHandleBitRateSliderChange);
    connect(m_pSpinboxBitRate, &QSpinBox::valueChanged,
            this, &UIRecordingVideoBitrateEditor::sltHandleBitRateSpinboxChange);
}
