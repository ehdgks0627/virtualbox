/* $Id: QITreeView.cpp 111658 2025-11-12 11:32:50Z sergey.dubov@oracle.com $ */
/** @file
 * VBox Qt GUI - Qt extensions: QITreeView class implementation.
 */

/*
 * Copyright (C) 2009-2025 Oracle and/or its affiliates.
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
#include <QDragLeaveEvent>
#include <QDragMoveEvent>
#include <QDropEvent>
#include <QMouseEvent>
#include <QPainter>
#include <QSortFilterProxyModel>
#include <QStack>

/* GUI includes: */
#include "QITreeView.h"
#include "UIAccessible.h"

/* Other VBox includes: */
#include "iprt/assert.h"


/** QAccessibleObject extension used as an accessibility interface for QITreeViewItem. */
class QIAccessibilityInterfaceForQITreeViewItem
    : public QAccessibleObject
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating QITreeViewItem accessibility interface: */
        if (pObject && strClassname == QLatin1String("QITreeViewItem"))
            return new QIAccessibilityInterfaceForQITreeViewItem(pObject);

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pObject to the base-class. */
    QIAccessibilityInterfaceForQITreeViewItem(QObject *pObject)
        : QAccessibleObject(pObject)
    {}

    /** Returns the role. */
    virtual QAccessible::Role role() const RT_OVERRIDE
    {
#ifdef VBOX_WS_MAC
            // WORKAROUND: macOS doesn't respect QAccessible::Tree/TreeItem roles.

            /* Return List for item with children, ListItem otherwise: */
            if (childCount() > 0)
               return QAccessible::List;
            return QAccessible::ListItem;
#else
            return QAccessible::TreeItem;
#endif
    }

    /** Returns the parent. */
    virtual QAccessibleInterface *parent() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITreeViewItem *pItem = item();
        AssertPtrReturn(pItem, 0);

        /* No parent for root item: */
        QITreeViewItem *pParentItem = pItem->parentItem();
        if (!pParentItem)
            return 0;

        /* Return parent-item interface if parent-item has
         * own parent (which means parent-item isn't root): */
        if (pParentItem->parentItem())
            return QAccessible::queryAccessibleInterface(pParentItem);
        /* Otherwise return parent-tree interface if it's
         * present (which means parent-item is root): */
        if (QITreeView *pParentTree = pParentItem->parentTree())
            return QAccessible::queryAccessibleInterface(pParentTree);

        /* Null by default: */
        return 0;
    }

    /** Returns the rect. */
    virtual QRect rect() const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(item(), QRect());
        AssertPtrReturn(item()->parentTree(), QRect());
        AssertPtrReturn(item()->parentTree()->viewport(), QRect());

        /* Calculate overall region: */
        QRegion region;
        /* Compose a stack of items to enumerate: */
        QStack<QITreeViewItem*> itemsToEnumerate;
        /* Initially push only iterated item into that stack: */
        itemsToEnumerate.push(item());
        /* While there are items to enumerate inside that stack: */
        while (!itemsToEnumerate.empty())
        {
            /* Take the top-most item from the stack: */
            QITreeViewItem *pItemToEnumerate = itemsToEnumerate.pop();

            /* Append that top-most item's rectangle to the region: */
            region += pItemToEnumerate->rect();

            /* Push that top-most item's children to the stack in
             * reverse order to process them in the correct order afterwards: */
            for (int i = pItemToEnumerate->childCount() - 1; i >= 0; --i)
                itemsToEnumerate.push(pItemToEnumerate->childItem(i));
        }

        /* Get the local rect: */
        const QRect  itemRectInViewport = region.boundingRect();
        const QSize  itemSize           = itemRectInViewport.size();
        const QPoint itemPosInViewport  = itemRectInViewport.topLeft();
        const QPoint itemPosInScreen    = item()->parentTree()->viewport()->mapToGlobal(itemPosInViewport);
        const QRect  itemRectInScreen   = QRect(itemPosInScreen, itemSize);

        /* Return the rect: */
        return itemRectInScreen;
    }

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(item(), 0);

        /* Return the number of children: */
        return item()->childCount();
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int iIndex) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(iIndex >= 0 && iIndex < childCount(), 0);
        QITreeViewItem *pThisItem = item();
        AssertPtrReturn(pThisItem, 0);
        QITreeView *pTree = pThisItem->parentTree();
        AssertPtrReturn(pTree, 0);
        QAbstractItemModel *pModel = pTree->model();
        AssertPtrReturn(pModel, 0);

        /* Acquire parent model-index: */
        const QModelIndex parentIndex = pThisItem->modelIndex();

        /* Acquire child-index: */
        const QModelIndex childIndex = pModel->index(iIndex, 0, parentIndex);
        /* Check whether we have proxy model set or source one otherwise: */
        const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);
        /* Acquire source-model child-index (can be the same as original if there is no proxy model): */
        const QModelIndex sourceChildIndex = pProxyModel ? pProxyModel->mapToSource(childIndex) : childIndex;

        /* Acquire child item: */
        QITreeViewItem *pItem = reinterpret_cast<QITreeViewItem*>(sourceChildIndex.internalPointer());
        /* Return child item's accessibility interface: */
        return QAccessible::queryAccessibleInterface(pItem);
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
        /* Sanity check: */
        QITreeViewItem *pItem = item();
        AssertPtrReturn(pItem, QAccessible::State());
        QITreeView *pTree = pItem->parentTree();
        AssertPtrReturn(pTree, QAccessible::State());
        QAbstractItemModel *pModel = pTree->model();
        AssertPtrReturn(pModel, QAccessible::State());

        /* Get current index: */
        const QModelIndex idxCurrent = pTree->currentIndex();

        /* Sanity check: */
        AssertReturn(idxCurrent.isValid(), QAccessible::State());

        /* Check whether we have proxy model set or source one otherwise: */
        const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);
        /* Acquire source-model child-index (can be the same as original if there is no proxy model): */
        const QModelIndex idxSourceCurrent = pProxyModel ? pProxyModel->mapToSource(idxCurrent) : idxCurrent;

        /* Get current item: */
        QITreeViewItem *pCurrentItem = static_cast<QITreeViewItem*>(idxSourceCurrent.internalPointer());

        /* Sanity check: */
        AssertPtrReturn(pCurrentItem, QAccessible::State());

        /* Compose the state: */
        QAccessible::State myState;
        myState.focusable = true;
        myState.selectable = true;
        if (   pTree->hasFocus()
            && pCurrentItem == pItem)
        {
            myState.focused = true;
            myState.selected = true;
        }
        const Qt::CheckState enmCheckState =
            pModel->data(pItem->modelIndex(), Qt::CheckStateRole).value<Qt::CheckState>();
        switch (enmCheckState)
        {
            case Qt::Checked:
                myState.checked = true;
                break;
            case Qt::PartiallyChecked:
                myState.checked = true;
                myState.checkStateMixed = true;
                break;
            default:
                break;
        }

        /* Return the state: */
        return myState;
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text enmTextRole) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(item(), QString());

        /* Return a text for the passed enmTextRole: */
        switch (enmTextRole)
        {
            case QAccessible::Name: return item()->text();
            default: break;
        }

        /* Null-string by default: */
        return QString();
    }

private:

    /** Returns corresponding QITreeViewItem. */
    QITreeViewItem *item() const { return qobject_cast<QITreeViewItem*>(object()); }
};


/** QAccessibleWidget extension used as an accessibility interface for QITreeView. */
class QIAccessibilityInterfaceForQITreeView
    : public QAccessibleWidget
#ifndef VBOX_WS_MAC
    , public QAccessibleSelectionInterface
#endif
    , public UIAccessibleAdvancedInterface
{
public:

    /** Returns an accessibility interface for passed @a strClassname and @a pObject. */
    static QAccessibleInterface *pFactory(const QString &strClassname, QObject *pObject)
    {
        /* Creating QITreeView accessibility interface: */
        if (pObject && strClassname == QLatin1String("QITreeView"))
            return new QIAccessibilityInterfaceForQITreeView(qobject_cast<QWidget*>(pObject));

        /* Null by default: */
        return 0;
    }

    /** Constructs an accessibility interface passing @a pWidget to the base-class. */
    QIAccessibilityInterfaceForQITreeView(QWidget *pWidget)
#ifdef VBOX_WS_MAC
        // WORKAROUND: macOS doesn't respect QAccessible::Tree/TreeItem roles.
        : QAccessibleWidget(pWidget, QAccessible::List)
#else
        : QAccessibleWidget(pWidget, QAccessible::Tree)
#endif
    {}

    /** Returns a specialized accessibility interface @a enmType. */
    virtual void *interface_cast(QAccessible::InterfaceType enmType) RT_OVERRIDE
    {
        const int iCase = static_cast<int>(enmType);
        switch (iCase)
        {
#ifdef VBOX_WS_MAC
            /// @todo Fix selection interface for macOS first of all!
#else
            case QAccessible::SelectionInterface:
                return static_cast<QAccessibleSelectionInterface*>(this);
#endif
            case UIAccessible::Advanced:
                return static_cast<UIAccessibleAdvancedInterface*>(this);
            default:
                break;
        }

        return 0;
    }

    /** Returns the number of children. */
    virtual int childCount() const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertPtrReturn(tree(), 0);

        /* Return the number of children: */
        return tree()->childCount();
    }

    /** Returns the child with the passed @a iIndex. */
    virtual QAccessibleInterface *child(int iIndex) const RT_OVERRIDE
    {
        /* Sanity check: */
        AssertReturn(iIndex >= 0, 0);
        QITreeView *pTree = tree();
        AssertPtrReturn(pTree, 0);
        QAbstractItemModel *pModel = pTree->model();
        AssertPtrReturn(pModel, 0);

        /* Prepare child-index: */
        QModelIndex childIndex;

        /* For Advanced interface enabled we have special processing: */
        if (isEnabled())
        {
            // WORKAROUND:
            // Qt's qtreeview class has a piece of accessibility code we do not like.
            // It's located in currentChanged() method and sends us iIndex calculated on
            // the basis of current model-index, instead of current qtreeviewitem index.
            // So qtreeview enumerates all tree-view rows/columns as children of level 0.
            // We are locking interface for the case and have special handling.
            //printf("Advanced iIndex: %d\n", iIndex);

            // Take into account we also have header with 'column count' indexes,
            // so we should start enumerating tree indexes since 'column count'.
            const int iColumnCount = pModel->columnCount();
            int iCurrentIndex = iColumnCount;

            // Search for sibling with corresponding index:
            childIndex = pModel->index(0, 0, pTree->rootIndex());
            while (childIndex.isValid() && iCurrentIndex < iIndex)
            {
                ++iCurrentIndex;
                if (iCurrentIndex % iColumnCount == 0)
                    childIndex = tree()->indexBelow(childIndex);
            }
        }
        else
        {
            //printf("Basic iIndex: %d\n", iIndex);

            /* By default we'll just get top-level index of required row: */
            childIndex = pModel->index(iIndex, 0, pTree->rootIndex());
        }

        /* Check whether we have proxy model set or source one otherwise: */
        const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);
        /* Acquire source-model child-index (can be the same as original if there is no proxy model): */
        const QModelIndex sourceChildIndex = pProxyModel ? pProxyModel->mapToSource(childIndex) : childIndex;

        /* Acquire child item: */
        QITreeViewItem *pItem = reinterpret_cast<QITreeViewItem*>(sourceChildIndex.internalPointer());
        /* Return child item's accessibility interface: */
        return QAccessible::queryAccessibleInterface(pItem);
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
        /* Sanity check: */
        AssertPtrReturn(tree(), QAccessible::State());

        /* Compose the state: */
        QAccessible::State myState;
        myState.focusable = true;
        if (tree()->hasFocus())
            myState.focused = true;

        /* Return the state: */
        return myState;
    }

    /** Returns a text for the passed @a enmTextRole. */
    virtual QString text(QAccessible::Text enmTextRole) const RT_OVERRIDE
    {
        /* Text for known roles: */
        switch (enmTextRole)
        {
            case QAccessible::Name:
            {
                /* Sanity check: */
                AssertPtrReturn(tree(), QString());

                /* Gather suitable text: */
                QString strText = tree()->toolTip();
                if (strText.isEmpty())
                    strText = tree()->whatsThis();
                return strText;
            }
            default:
                break;
        }

        /* Null string by default: */
        return QString();
    }

#ifndef VBOX_WS_MAC
    /** Returns the total number of selected accessible items. */
    virtual int selectedItemCount() const RT_OVERRIDE
    {
        /* For now we are interested in just first one selected item: */
        return 1;
    }

    /** Returns the list of selected accessible items. */
    virtual QList<QAccessibleInterface*> selectedItems() const RT_OVERRIDE
    {
        /* Sanity check: */
        QITreeView *pTree = tree();
        AssertPtrReturn(pTree, QList<QAccessibleInterface*>());
        QAbstractItemModel *pModel = pTree->model();
        AssertPtrReturn(pModel, QList<QAccessibleInterface*>());

        /* Get current index: */
        const QModelIndex idxCurrent = pTree->currentIndex();

        /* Sanity check: */
        AssertReturn(idxCurrent.isValid(), QList<QAccessibleInterface*>());

        /* Check whether we have proxy model set or source one otherwise: */
        const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);
        /* Acquire source-model child-index (can be the same as original if there is no proxy model): */
        const QModelIndex idxSourceCurrent = pProxyModel ? pProxyModel->mapToSource(idxCurrent) : idxCurrent;

        /* Get current item: */
        QITreeViewItem *pCurrentItem = static_cast<QITreeViewItem*>(idxSourceCurrent.internalPointer());

        /* Sanity check: */
        AssertPtrReturn(pCurrentItem, QList<QAccessibleInterface*>());

        /* For now we are interested in just first one selected item: */
        // printf("item selected: %s\n", pCurrentItem->text().toUtf8().constData());
        return QList<QAccessibleInterface*>() << QAccessible::queryAccessibleInterface(pCurrentItem);
    }

    /** Adds childItem to the selection. */
    virtual bool select(QAccessibleInterface *) RT_OVERRIDE
    {
        /// @todo implement
        return false;
    }

    /** Removes childItem from the selection. */
    virtual bool unselect(QAccessibleInterface *) RT_OVERRIDE
    {
        /// @todo implement
        return false;
    }

    /** Selects all accessible child items. */
    virtual bool selectAll() RT_OVERRIDE
    {
        /// @todo implement
        return false;
    }

    /** Unselects all accessible child items. */
    virtual bool clear() RT_OVERRIDE
    {
        /// @todo implement
        return false;
    }
#endif /* VBOX_WS_MAC */

private:

    /** Returns corresponding QITreeView. */
    QITreeView *tree() const { return qobject_cast<QITreeView*>(widget()); }
};


/*********************************************************************************************************************************
*   Class QITreeViewItem implementation.                                                                                         *
*********************************************************************************************************************************/

int QITreeViewItem::childCount() const
{
    /* Sanity check: */
    AssertPtrReturn(parentTree(), 0);
    AssertPtrReturn(parentTree()->model(), 0);

    /* Return the number of children model has: */
    return parentTree()->model()->rowCount(modelIndex());
}

QRect QITreeViewItem::rect() const
{
    /* We can only ask the parent-tree for a rectangle: */
    if (parentTree())
    {
        /* Acquire parent-tree model: */
        const QAbstractItemModel *pModel = parentTree()->model();
        AssertPtrReturn(pModel, QRect());

        /* Acquire zero-column rectangle: */
        QModelIndex itemIndex = modelIndex();
        QRect rect = parentTree()->visualRect(itemIndex);
        /* Enumerate all the remaining columns: */
        for (int i = 1; i < pModel->columnCount(); ++i)
        {
            /* Acquire enumerated column rectangle: */
            QModelIndex itemIndexI = pModel->index(itemIndex.row(), i, itemIndex.parent());
            QRegion cumulativeRegion(rect);
            cumulativeRegion += parentTree()->visualRect(itemIndexI);
            rect = cumulativeRegion.boundingRect();
        }
        /* Total rect finally: */
        return rect;
    }
    /* Empty rect by default: */
    return QRect();
}

QModelIndex QITreeViewItem::modelIndex() const
{
    /* Acquire model: */
    const QAbstractItemModel *pModel = parentTree()->model();
    /* Check whether we have proxy model set or source one otherwise: */
    const QSortFilterProxyModel *pProxyModel = qobject_cast<const QSortFilterProxyModel*>(pModel);

    /* Acquire root model-index: */
    const QModelIndex rootIndex = parentTree()->rootIndex();
    /* Acquire source root model-index, which can be the same as root model-index: */
    const QModelIndex rootSourceModelIndex = pProxyModel ? pProxyModel->mapToSource(rootIndex) : rootIndex;

    /* Check whether we have root model-index here: */
    if (   rootSourceModelIndex.internalPointer()
        && rootSourceModelIndex.internalPointer() == this)
        return rootIndex;

    /* Determine our parent model-index: */
    const QModelIndex parentIndex = parentItem() ? parentItem()->modelIndex() : rootIndex;

    /* Determine our position inside parent: */
    int iPositionInParent = -1;
    for (int i = 0; i < pModel->rowCount(parentIndex); ++i)
    {
        /* Acquire child model-index: */
        const QModelIndex childIndex = pModel->index(i, 0, parentIndex);
        /* Acquire source child model-index, which can be the same as child model-index: */
        const QModelIndex childSourceModelIndex = pProxyModel ? pProxyModel->mapToSource(childIndex) : childIndex;

        /* Check whether we have child model-index here: */
        if (   childSourceModelIndex.internalPointer()
            && childSourceModelIndex.internalPointer() == this)
        {
            iPositionInParent = i;
            break;
        }
    }
    /* Make sure we found something: */
    if (iPositionInParent == -1)
        return QModelIndex();

    /* Return model-index as child of parent model-index: */
    return pModel->index(iPositionInParent, 0, parentIndex);
}


/*********************************************************************************************************************************
*   Class QITreeView implementation.                                                                                             *
*********************************************************************************************************************************/

QITreeView::QITreeView(QWidget *pParent)
    : QTreeView(pParent)
{
    /* Prepare all: */
    prepare();
}

int QITreeView::childCount() const
{
    /* Sanity check: */
    AssertPtrReturn(model(), 0);

    /* Acquire required model-index, that can be root-index if specified
     * or null index otherwise, in that case we return the amount of top-level children: */
    const QModelIndex rtIndex = rootIndex();
    const QModelIndex requiredIndex = rtIndex.isValid() ? rtIndex : QModelIndex();
    return model()->rowCount(requiredIndex);
}

void QITreeView::currentChanged(const QModelIndex &current, const QModelIndex &previous)
{
    /* A call to base-class needs to be executed by advanced interface: */
    UIAccessibleAdvancedInterfaceLocker locker(this);
    Q_UNUSED(locker);

    /* Notify listeners about it: */
    emit currentItemChanged(current, previous);
    /* Call to base-class: */
    QTreeView::currentChanged(current, previous);
}

void QITreeView::selectionChanged(const QItemSelection &selected, const QItemSelection &deselected)
{
    /* A call to base-class needs to be executed by advanced interface: */
    UIAccessibleAdvancedInterfaceLocker locker(this);
    Q_UNUSED(locker);

    /* Call to base-class: */
    QTreeView::selectionChanged(selected, deselected);
}

void QITreeView::drawBranches(QPainter *pPainter, const QRect &rect, const QModelIndex &index) const
{
    /* Notify listeners about it: */
    emit drawItemBranches(pPainter, rect, index);
    /* Call to base-class: */
    QTreeView::drawBranches(pPainter, rect, index);
}

void QITreeView::mouseMoveEvent(QMouseEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit mouseMoved(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::mouseMoveEvent(pEvent);
}

void QITreeView::mousePressEvent(QMouseEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit mousePressed(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::mousePressEvent(pEvent);
}

void QITreeView::mouseReleaseEvent(QMouseEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit mouseReleased(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::mouseReleaseEvent(pEvent);
}

void QITreeView::mouseDoubleClickEvent(QMouseEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit mouseDoubleClicked(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::mouseDoubleClickEvent(pEvent);
}

void QITreeView::dragEnterEvent(QDragEnterEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit dragEntered(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::dragEnterEvent(pEvent);
}

void QITreeView::dragMoveEvent(QDragMoveEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit dragMoved(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::dragMoveEvent(pEvent);
}

void QITreeView::dragLeaveEvent(QDragLeaveEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit dragLeft(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::dragLeaveEvent(pEvent);
}

void QITreeView::dropEvent(QDropEvent *pEvent)
{
    /* Reject event initially: */
    pEvent->setAccepted(false);
    /* Notify listeners about event allowing them to handle it: */
    emit dragDropped(pEvent);
    /* Call to base-class only if event was not yet accepted: */
    if (!pEvent->isAccepted())
        QTreeView::dropEvent(pEvent);
}

void QITreeView::prepare()
{
    /* Install QITreeViewItem accessibility interface factory: */
    QAccessible::installFactory(QIAccessibilityInterfaceForQITreeViewItem::pFactory);
    /* Install QITreeView accessibility interface factory: */
    QAccessible::installFactory(QIAccessibilityInterfaceForQITreeView::pFactory);

    /* Mark header hidden: */
    setHeaderHidden(true);
    /* Mark root hidden: */
    setRootIsDecorated(false);
}
