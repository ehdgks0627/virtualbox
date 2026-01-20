/* $Id: UIDetailsView.cpp 112650 2026-01-20 15:02:17Z sergey.dubov@oracle.com $ */
/** @file
 * VBox Qt GUI - UIDetailsView class implementation.
 */

/*
 * Copyright (C) 2012-2026 Oracle and/or its affiliates.
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
#include <QAccessibleWidget>
#include <QApplication>
#include <QScrollBar>

/* GUI includes: */
#include "UICommon.h"
#include "UIDetailsItem.h"
#include "UIDetailsModel.h"
#include "UIDetailsView.h"
#include "UITranslationEventListener.h"

/* Other VBox includes: */
#include <iprt/assert.h>


/** QAccessibleWidget extension used as an accessibility interface for Details-view. */
class UIAccessibilityInterfaceForUIDetailsView : public QAccessibleWidget
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating Details-view accessibility interface: */
        if (pObject && strClassname == QLatin1String("UIDetailsView"))
            return new UIAccessibilityInterfaceForUIDetailsView(qobject_cast<QWidget*>(pObject));

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pWidget to the base-class. */
    UIAccessibilityInterfaceForUIDetailsView(QWidget *pWidget)
        : QAccessibleWidget(pWidget, QAccessible::List)
    {}

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(view(), 0);
        AssertPtrReturn(view()->model(), 0);
        AssertPtrReturn(view()->model()->root(), 0);

        /* What amount of children root has? */
        const int cChildCount = view()->model()->root()->items().size();
        /* Return amount of children root has (if there are many children): */
        if (cChildCount > 1)
            return cChildCount;

        /* Sanity check: */
        AssertPtrReturn(view()->model()->root()->items().first(), 0);

        /* Return the number of children lone root child has (otherwise): */
        return view()->model()->root()->items().first()->items().size();
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int iIndex) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(iIndex >= 0 && iIndex < childCount(), 0);
        AssertPtrReturn(view(), 0);
        AssertPtrReturn(view()->model(), 0);
        AssertPtrReturn(view()->model()->root(), 0);

        /* What amount of children root has? */
        const int cChildCount = view()->model()->root()->items().size();
        /* Return the root child with the passed iIndex (if there are many children): */
        if (cChildCount > 1)
            return QAccessible::queryAccessibleInterface(view()->model()->root()->items().value(iIndex));

        /* Sanity check: */
        AssertPtrReturn(view()->model()->root()->items().first(), 0);

        /* Return the lone root child's child with the passed iIndex (otherwise): */
        return QAccessible::queryAccessibleInterface(view()->model()->root()->items().first()->items().value(iIndex));
    }

    /** Returns the index of passed @a pChild. */
    virtual int indexOfChild(const QAccessibleInterface *pChild) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(pChild, -1);

        /* Acquire item itself: */
        UIDetailsItem *pChildItem = qobject_cast<UIDetailsItem*>(pChild->object());

        /* Sanity check: */
        AssertPtrReturn(pChildItem, -1);
        AssertPtrReturn(pChildItem->parentItem(), -1);

        /* Return the index of item in it's parent: */
        return pChildItem->parentItem()->items().indexOf(pChildItem);
    }

    /** Returns the state. */
    virtual QAccessible::State state() const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(view(), QAccessible::State());

        /* Compose the state: */
        QAccessible::State myState;
        myState.focusable = true;
        if (view()->hasFocus())
            myState.focused = true;

        /* Return the state: */
        return myState;
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text enmTextRole) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(view(), QString());

        /* Text for known roles: */
        switch (enmTextRole)
        {
            case QAccessible::Name: return view()->whatsThis();
            default: break;
        }

        /* Null string by default: */
        return QString();
    }

private:

    /** Returns corresponding Details-view. */
    UIDetailsView *view() const { return qobject_cast<UIDetailsView*>(widget()); }
};


UIDetailsView::UIDetailsView(QWidget *pParent)
    : QIGraphicsView(pParent)
    , m_iMinimumWidthHint(0)
{
    prepare();
}

void UIDetailsView::setModel(UIDetailsModel *pDetailsModel)
{
    m_pDetailsModel = pDetailsModel;
}

UIDetailsModel *UIDetailsView::model() const
{
    return m_pDetailsModel;
}

void UIDetailsView::sltMinimumWidthHintChanged(int iHint)
{
    /* Is there something changed? */
    if (m_iMinimumWidthHint == iHint)
        return;

    /* Remember new value: */
    m_iMinimumWidthHint = iHint;
    if (m_iMinimumWidthHint <= 0)
        m_iMinimumWidthHint = 1;

    /* Set minimum view width according passed width-hint: */
    setMinimumWidth(2 * frameWidth() + m_iMinimumWidthHint + verticalScrollBar()->sizeHint().width());

    /* Update scene-rect: */
    updateSceneRect();
}

void UIDetailsView::sltRetranslateUI()
{
    /* Translate this: */
    setWhatsThis(tr("Contains a list of Virtual Machine details."));
}

void UIDetailsView::resizeEvent(QResizeEvent *pEvent)
{
    /* Call to base-class: */
    QIGraphicsView::resizeEvent(pEvent);
    /* Notify listeners: */
    emit sigResized();

    /* Update everything: */
    updateSceneRect();
}

void UIDetailsView::prepare()
{
    /* Install Details-view accessibility interface factory: */
    QAccessible::installFactory(UIAccessibilityInterfaceForUIDetailsView::pFactory);

    /* Prepares everything: */
    prepareThis();

    /* Update everything: */
    updateSceneRect();

    /* Translate finally: */
    sltRetranslateUI();
    connect(&translationEventListener(), &UITranslationEventListener::sigRetranslateUI,
            this, &UIDetailsView::sltRetranslateUI);
}

void UIDetailsView::prepareThis()
{
    /* Prepare palette: */
    preparePalette();

    /* Prepare frame: */
    setFrameShape(QFrame::NoFrame);
    setFrameShadow(QFrame::Plain);
    setAlignment(Qt::AlignLeft | Qt::AlignTop);

    /* Prepare scroll-bars policy: */
    setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
    setVerticalScrollBarPolicy(Qt::ScrollBarAlwaysOff);

    /* Prepare connections: */
    connect(&uiCommon(), &UICommon::sigThemeChange,
            this, &UIDetailsView::sltUpdatePalette);
}

void UIDetailsView::preparePalette()
{
    QPalette pal = QApplication::palette();
    pal.setColor(QPalette::Active, QPalette::Base, pal.color(QPalette::Active, QPalette::Window));
    pal.setColor(QPalette::Inactive, QPalette::Base, pal.color(QPalette::Inactive, QPalette::Window));
    setPalette(pal);
}

void UIDetailsView::updateSceneRect()
{
    setSceneRect(0, 0, m_iMinimumWidthHint, height());
}
