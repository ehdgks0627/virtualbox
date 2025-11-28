/* $Id: QITableView.cpp 111936 2025-11-28 15:38:41Z sergey.dubov@oracle.com $ */
/** @file
 * VBox Qt GUI - Qt extensions: QITableView class implementation.
 */

/*
 * Copyright (C) 2010-2025 Oracle and/or its affiliates.
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
#include <QSortFilterProxyModel>

/* GUI includes: */
#include "QIStyledItemDelegate.h"
#include "QITableView.h"

/* Other VBox includes: */
#include "iprt/assert.h"


/** QAccessibleObject extension used as an accessibility interface for QITableViewCell. */
class QIAccessibilityInterfaceForQITableViewCell
    : public QAccessibleObject
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating QITableViewCell accessibility interface: */
        if (pObject && strClassname == QLatin1String("QITableViewCell"))
            return new QIAccessibilityInterfaceForQITableViewCell(pObject);

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pObject to the base-class. */
    QIAccessibilityInterfaceForQITableViewCell(QObject *pObject)
        : QAccessibleObject(pObject)
    {}

    /** Returns the role. */
    virtual QAccessible::Role role() const RT_OVERRIDE
    {
        /* Cell by default: */
        return QAccessible::Cell;
    }

    /** Returns the parent. */
    virtual QAccessibleInterface *parent() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewCell *pCell = cell();
        AssertPtrReturn(pCell, 0);

        /* Return the parent: */
        return QAccessible::queryAccessibleInterface(pCell->row());
    }

    /** Returns the rect. */
    virtual QRect rect() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewCell *pCell = cell();
        AssertPtrReturn(pCell, QRect());
        QITableViewRow *pRow = pCell->row();
        AssertPtrReturn(pRow, QRect());
        QITableView *pTable = pRow->table();
        AssertPtrReturn(pTable, QRect());
        QWidget *pViewport = pTable->viewport();
        AssertPtrReturn(pViewport, QRect());
        QAccessibleInterface *pParent = parent();
        AssertPtrReturn(pParent, QRect());
        QAccessibleInterface *pParentOfParent = pParent->parent();
        AssertPtrReturn(pParentOfParent, QRect());

        /* Calculate local item coordinates: */
        const int iIndexInParent = pParent->indexOfChild(this);
        const int iParentIndexInParent = pParentOfParent->indexOfChild(pParent);
        const int iX = pTable->columnViewportPosition(iIndexInParent);
        const int iY = pTable->rowViewportPosition(iParentIndexInParent);
        const int iWidth = pTable->columnWidth(iIndexInParent);
        const int iHeight = pTable->rowHeight(iParentIndexInParent);

        /* Map local item coordinates to global: */
        const QPoint itemPosInScreen = pViewport->mapToGlobal(QPoint(iX, iY));

        /* Return item rectangle: */
        return QRect(itemPosInScreen, QSize(iWidth, iHeight));
    }

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        return 0;
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int /* iIndex */) const RT_OVERRIDE
    {
        return 0;
    }

    /** Returns the index of the passed @a pChild. */
    virtual int indexOfChild(const QAccessibleInterface * /* pChild */) const RT_OVERRIDE
    {
        return -1;
    }

    /** Returns the state. */
    virtual QAccessible::State state() const RT_OVERRIDE
    {
        return QAccessible::State();
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text enmTextRole) const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewCell *pCell = cell();
        AssertPtrReturn(pCell, QString());

        /* Return a text for the passed enmTextRole: */
        switch (enmTextRole)
        {
            case QAccessible::Name: return pCell->text();
            default: break;
        }

        /* Null-string by default: */
        return QString();
    }

private:

    /** Returns corresponding QITableViewCell. */
    QITableViewCell *cell() const { return qobject_cast<QITableViewCell*>(object()); }
};


/** QAccessibleObject extension used as an accessibility interface for QITableViewRow. */
class QIAccessibilityInterfaceForQITableViewRow
    : public QAccessibleObject
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating QITableViewRow accessibility interface: */
        if (pObject && strClassname == QLatin1String("QITableViewRow"))
            return new QIAccessibilityInterfaceForQITableViewRow(pObject);

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pObject to the base-class. */
    QIAccessibilityInterfaceForQITableViewRow(QObject *pObject)
        : QAccessibleObject(pObject)
    {}

    /** Returns the role. */
    virtual QAccessible::Role role() const RT_OVERRIDE
    {
        /* Row by default: */
        return QAccessible::Row;
    }

    /** Returns the parent. */
    virtual QAccessibleInterface *parent() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewRow *pRow = row();
        AssertPtrReturn(pRow, 0);

        /* Return the parent: */
        return QAccessible::queryAccessibleInterface(pRow->table());
    }

    /** Returns the rect. */
    virtual QRect rect() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewRow *pRow = row();
        AssertPtrReturn(pRow, QRect());
        QITableView *pTable = pRow->table();
        AssertPtrReturn(pTable, QRect());
        QWidget *pViewport = pTable->viewport();
        AssertPtrReturn(pViewport, QRect());
        QAccessibleInterface *pParent = parent();
        AssertPtrReturn(pParent, QRect());

        /* Calculate local item coordinates: */
        const int iIndexInParent = pParent->indexOfChild(this);
        const int iX = pTable->columnViewportPosition(0);
        const int iY = pTable->rowViewportPosition(iIndexInParent);
        int iWidth = 0;
        int iHeight = 0;
        for (int i = 0; i < childCount(); ++i)
            iWidth += pTable->columnWidth(i);
        iHeight += pTable->rowHeight(iIndexInParent);

        /* Map local item coordinates to global: */
        const QPoint itemPosInScreen = pViewport->mapToGlobal(QPoint(iX, iY));

        /* Return item rectangle: */
        return QRect(itemPosInScreen, QSize(iWidth, iHeight));
    }

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableViewRow *pRow = row();
        AssertPtrReturn(pRow, 0);

        /* Return the number of children: */
        return pRow->childCount();
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int iIndex) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(iIndex >= 0 && iIndex < childCount(), 0);
        QITableViewRow *pRow = row();
        AssertPtrReturn(pRow, 0);

        /* Return the child with the passed iIndex: */
        return QAccessible::queryAccessibleInterface(pRow->childItem(iIndex));
    }

    /** Returns the index of the passed @a pChild. */
    virtual int indexOfChild(const QAccessibleInterface *pChild) const RT_OVERRIDE
    {
        /* Search for corresponding child: */
        for (int i = 0; i < childCount(); ++i)
            if (child(i) == pChild)
                return i;

        /* -1 by default: */
        return -1;
    }

    /** Returns the state. */
    virtual QAccessible::State state() const RT_OVERRIDE
    {
        return QAccessible::State();
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text enmTextRole) const RT_OVERRIDE
    {
        /* Return a text for the passed enmTextRole: */
        switch (enmTextRole)
        {
            case QAccessible::Name: return childCount() > 0 && child(0) ? child(0)->text(enmTextRole) : QString();
            default: break;
        }

        /* Null-string by default: */
        return QString();
    }

private:

    /** Returns corresponding QITableViewRow. */
    QITableViewRow *row() const { return qobject_cast<QITableViewRow*>(object()); }
};


/** QAccessibleWidget extension used as an accessibility interface for QITableView. */
class QIAccessibilityInterfaceForQITableView
    : public QAccessibleWidget
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating QITableView accessibility interface: */
        if (pObject && strClassname == QLatin1String("QITableView"))
            return new QIAccessibilityInterfaceForQITableView(qobject_cast<QWidget*>(pObject));

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pWidget to the base-class. */
    QIAccessibilityInterfaceForQITableView(QWidget *pWidget)
        : QAccessibleWidget(pWidget, QAccessible::List)
    {}

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableView *pTable = table();
        AssertPtrReturn(pTable, 0);
        QAbstractItemModel *pModel = pTable->model();
        AssertPtrReturn(pModel, 0);

        /* Return the number of children: */
        return pModel->rowCount();
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int iIndex) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(iIndex >= 0, 0);
        QITableView *pTable = table();
        AssertPtrReturn(pTable, 0);
        QAbstractItemModel *pModel = pTable->model();
        AssertPtrReturn(pModel, 0);

        /* Real index might be different: */
        int iRealRowIndex = iIndex;

        // WORKAROUND:
        // For a table-views Qt accessibility code has a hard-coded architecture which we do not like
        // but have to live with, this architecture enumerates cells including header column and row,
        // so Qt can try to address our interface with index which surely out of bounds by our laws.
        // Let's assume that's exactly the case and try to enumerate cells including header column and row.
        if (iRealRowIndex >= childCount())
        {
            // Split delimeter is overall column count, including vertical header:
            const int iColumnCount = pModel->columnCount() + 1 /* v_header */;
            // Real index is zero-based, incoming is 1-based:
            const int iRealIndex = iIndex - 1;
            // Real row index, excluding horizontal header:
            iRealRowIndex = iRealIndex / iColumnCount - 1 /* h_header */;
            // printf("Invalid index: %d, Actual index: %d\n", iIndex, iRealRowIndex);
        }

        /* Make sure index fits the bounds finally: */
        if (iRealRowIndex >= childCount())
            return 0;

        /* Acquire child-index: */
        const QModelIndex childIndex = pModel->index(iRealRowIndex, 0);
        /* Check whether we have proxy model set or source one otherwise: */
        const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);
        /* Acquire source-model child-index (can be the same as original if there is no proxy model): */
        const QModelIndex sourceChildIndex = pProxyModel ? pProxyModel->mapToSource(childIndex) : childIndex;

        /* Acquire row item: */
        QITableViewRow *pRow = static_cast<QITableViewRow*>(sourceChildIndex.internalPointer());
        /* Return row's accessibility interface: */
        return QAccessible::queryAccessibleInterface(pRow);
    }

    /** Returns the index of the passed @a pChild. */
    virtual int indexOfChild(const QAccessibleInterface *pChild) const RT_OVERRIDE
    {
        /* Search for corresponding child: */
        for (int i = 0; i < childCount(); ++i)
            if (child(i) == pChild)
                return i;

        /* -1 by default: */
        return -1;
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text /*enmTextRole*/) const RT_OVERRIDE
    {
        /* Sanity check: */
        QITableView *pTable = table();
        AssertPtrReturn(pTable, QString());

        /* Return table whats-this: */
        return pTable->whatsThis();
    }

private:

    /** Returns corresponding QITableView. */
    QITableView *table() const { return qobject_cast<QITableView*>(widget()); }
};


/*********************************************************************************************************************************
*   Class QITableView implementation.                                                                                            *
*********************************************************************************************************************************/

QITableView::QITableView(QWidget *pParent)
    : QTableView(pParent)
{
    /* Install QITableViewCell accessibility interface factory: */
    QAccessible::installFactory(QIAccessibilityInterfaceForQITableViewCell::pFactory);
    /* Install QITableViewRow accessibility interface factory: */
    QAccessible::installFactory(QIAccessibilityInterfaceForQITableViewRow::pFactory);
    /* Install QITableView accessibility interface factory: */
    QAccessible::installFactory(QIAccessibilityInterfaceForQITableView::pFactory);

    /* Delete old delegate: */
    delete itemDelegate();
    /* Create new delegate: */
    QIStyledItemDelegate *pStyledItemDelegate = new QIStyledItemDelegate(this);
    if (pStyledItemDelegate)
    {
        /* Assign newly created delegate to the table: */
        setItemDelegate(pStyledItemDelegate);
        /* Connect newly created delegate to the table: */
        connect(pStyledItemDelegate, &QIStyledItemDelegate::sigEditorCreated,
                this, &QITableView::sltEditorCreated);
    }
}

QITableView::~QITableView()
{
    /* Disconnect all the editors prematurelly: */
    foreach (QObject *pEditor, m_editors.values())
        disconnect(pEditor, 0, this, 0);
}

void QITableView::makeSureEditorDataCommitted()
{
    /* Do we have current editor at all? */
    QObject *pEditorObject = m_editors.value(currentIndex());
    if (pEditorObject && pEditorObject->isWidgetType())
    {
        /* Cast the editor to widget type: */
        QWidget *pEditor = qobject_cast<QWidget*>(pEditorObject);
        AssertPtrReturnVoid(pEditor);
        {
            /* Commit the editor data and closes it: */
            commitData(pEditor);
            closeEditor(pEditor, QAbstractItemDelegate::SubmitModelCache);
        }
    }
}

void QITableView::currentChanged(const QModelIndex &current, const QModelIndex &previous)
{
    /* Notify listeners about index changed: */
    emit sigCurrentChanged(current, previous);
    /* Call to base-class: */
    QTableView::currentChanged(current, previous);
}

void QITableView::selectionChanged(const QItemSelection &selected, const QItemSelection &deselected)
{
    /* Notify listeners about index changed: */
    emit sigSelectionChanged(selected, deselected);
    /* Call to base-class: */
    QTableView::selectionChanged(selected, deselected);
}

void QITableView::sltEditorCreated(QWidget *pEditor, const QModelIndex &index)
{
    /* Connect created editor to the table and store it: */
    connect(pEditor, &QWidget::destroyed, this, &QITableView::sltEditorDestroyed);
    m_editors[index] = pEditor;
}

void QITableView::sltEditorDestroyed(QObject *pEditor)
{
    /* Clear destroyed editor from the table: */
    const QModelIndex index = m_editors.key(pEditor);
    AssertReturnVoid(index.isValid());
    m_editors.remove(index);
}
